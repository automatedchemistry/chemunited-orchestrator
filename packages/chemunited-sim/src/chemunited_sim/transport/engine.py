"""Per-step FIFO transport engine for chemunited-sim.

:func:`advance` moves pockets one step forward along every transport edge
according to the signed volumetric flows in a :class:`HydraulicState`.

:func:`inject` inserts inventory-emitted pockets into edge queues at the
correct inflow end, ready for the next call to :func:`advance`.
"""

from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass

from chemunited_core.common.enums import PhaseKind
from chemunited_core.components.enums import InternalEdgeRole
from chemunited_core.compounds import COMPOUNDS
from chemunited_core.compounds.entity import IDEAL_GAS_CONSTANT
from loguru import logger

from ..adapter.models import HydraulicEdge, HydraulicGraph
from ..common.constant import (
    AMBIENT_TEMPERATURE_K,
    ATMOSPHERE_PRESSURE_PA,
    DEFICIT_FILL_ABS_TOL,
    DEFICIT_FILL_REL_TOL,
    MAX_JUNCTION_HOPS,
    MIN_POCKET_VOLUME,
)
from ..common.edges import is_hydraulically_closed
from ..hydraulics.models import HydraulicState
from .junction import merge_arriving_pockets
from .models import Pocket, TransportResult, TransportState

# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

_CP_CACHE: dict[tuple[str, PhaseKind], float] = {}


def _scale_pocket(pocket: Pocket, fraction: float) -> Pocket:
    """Return a new Pocket with volume and species scaled by *fraction*."""
    return Pocket(
        phase_kind=pocket.phase_kind,
        volume=pocket.volume * fraction,
        species_moles={k: v * fraction for k, v in pocket.species_moles.items()},
        temperature=pocket.temperature,
        pressure=pocket.pressure,
    )


def _pop_volume(
    queue: deque[Pocket],
    dV: float,
    from_left: bool,
) -> list[Pocket]:
    """Pop up to *dV* m³ of pockets from *queue*, splitting the boundary pocket.

    Parameters
    ----------
    queue:
        The edge queue to drain (modified in place).
    dV:
        Volume to extract in m³.
    from_left:
        ``True`` to pop from the left end (destination-ward; used when
        ``Q > 0``).  ``False`` to pop from the right end (origin-ward;
        used when ``Q < 0``).

    Returns
    -------
    list[Pocket]
        Exiting pockets.  Their total volume equals *dV* unless the queue
        ran dry (total < *dV*).
    """
    exiting: list[Pocket] = []
    accumulated = 0.0

    while queue and accumulated < dV:
        p = queue.popleft() if from_left else queue.pop()
        remaining = dV - accumulated

        if p.volume <= remaining:
            exiting.append(p)
            accumulated += p.volume
        else:
            # Pocket straddles the displacement boundary — split it.
            exit_frac = remaining / p.volume
            exiting.append(_scale_pocket(p, exit_frac))
            stay = _scale_pocket(p, 1.0 - exit_frac)
            if from_left:
                queue.appendleft(stay)
            else:
                queue.append(stay)
            break

    return exiting


def _build_indices(
    graph: HydraulicGraph,
) -> tuple[
    dict[str, list[tuple[str, HydraulicEdge]]],
    dict[str, list[tuple[str, HydraulicEdge]]],
]:
    """Build node-to-edges lookup tables for JUNCTION and TRANSPORT edges.

    Returns
    -------
    junction_neighbors:
        ``node_id → [(neighbor_node_id, HydraulicEdge), ...]`` for every
        JUNCTION edge touching that node.
    transport_by_node:
        ``node_id → [(edge_id, HydraulicEdge), ...]`` for every TRANSPORT
        edge whose origin or destination is that node.
    """
    junction_neighbors: dict[str, list[tuple[str, HydraulicEdge]]] = defaultdict(list)
    transport_by_node: dict[str, list[tuple[str, HydraulicEdge]]] = defaultdict(list)

    for eid, edge in graph.edges.items():
        if edge.role == InternalEdgeRole.JUNCTION:
            junction_neighbors[edge.origin_node_id].append(
                (edge.destination_node_id, edge)
            )
            junction_neighbors[edge.destination_node_id].append(
                (edge.origin_node_id, edge)
            )
        elif edge.role == InternalEdgeRole.TRANSPORT:
            transport_by_node[edge.origin_node_id].append((eid, edge))
            transport_by_node[edge.destination_node_id].append((eid, edge))

    return junction_neighbors, transport_by_node


def _outgoing_transport_dv(
    node_id: str,
    hyd_state: HydraulicState,
    dt: float,
    transport_by_node: dict[str, list[tuple[str, HydraulicEdge]]],
) -> dict[str, float]:
    """Return outgoing transport-edge displaced volumes from *node_id*."""
    outgoing: dict[str, float] = {}
    for edge_id, edge in transport_by_node.get(node_id, []):
        Q = hyd_state.flows.get(edge_id, 0.0)
        away_from_node = (edge.origin_node_id == node_id and Q > MIN_POCKET_VOLUME) or (
            edge.destination_node_id == node_id and Q < -MIN_POCKET_VOLUME
        )
        if away_from_node:
            dV = abs(Q) * dt
            if dV >= MIN_POCKET_VOLUME:
                outgoing[edge_id] = dV
    return outgoing


def _stage_transport_injections(
    pocket: Pocket,
    outgoing_dv: dict[str, float],
    staged: dict[str, list[Pocket]],
) -> None:
    """Split *pocket* across outgoing transport edges for later injection."""
    total_out = sum(outgoing_dv.values())
    if total_out < MIN_POCKET_VOLUME:
        return

    for edge_id, dV in outgoing_dv.items():
        frac = dV / total_out
        fragment = _scale_pocket(pocket, frac)
        if fragment.volume >= MIN_POCKET_VOLUME:
            staged[edge_id].append(fragment)


def _inject_staged_transport(
    new_queues: dict[str, deque[Pocket]],
    staged: dict[str, list[Pocket]],
    hyd_state: HydraulicState,
) -> None:
    """Inject staged pass-through pockets into transport queues."""
    for edge_id, pockets in staged.items():
        queue = new_queues.get(edge_id)
        if queue is None:
            continue
        Q = hyd_state.flows.get(edge_id, 0.0)
        for pocket in pockets:
            if Q >= 0:
                queue.append(pocket)
            else:
                queue.appendleft(pocket)


def _edge_capacity(edge: HydraulicEdge) -> float:
    """Return geometric capacity for a transport edge."""
    if edge.length <= 0.0 or edge.diameter <= 0.0:
        return 0.0
    return math.pi * (edge.diameter / 2.0) ** 2 * edge.length


def _fill_carrier_deficits(
    graph: HydraulicGraph,
    new_queues: dict[str, deque[Pocket]],
    hyd_state: HydraulicState,
) -> None:
    """Pad underfilled transport edges with air carrier pockets."""
    for edge_id, queue in new_queues.items():
        edge = graph.edges.get(edge_id)
        if edge is None or edge.role != InternalEdgeRole.TRANSPORT:
            continue
        capacity = _edge_capacity(edge)
        if capacity <= 0.0:
            continue

        volume = sum(p.volume for p in queue)
        deficit = capacity - volume
        tolerance = max(DEFICIT_FILL_ABS_TOL, DEFICIT_FILL_REL_TOL * capacity)
        if deficit < tolerance:
            continue

        Q = hyd_state.flows.get(edge_id, 0.0)
        inflow_node_id = edge.origin_node_id if Q >= 0.0 else edge.destination_node_id
        pressure = hyd_state.pressures.get(inflow_node_id, ATMOSPHERE_PRESSURE_PA)
        n_air = pressure * deficit / (IDEAL_GAS_CONSTANT * AMBIENT_TEMPERATURE_K)
        carrier = Pocket(
            phase_kind=PhaseKind.GAS,
            volume=deficit,
            species_moles={"air": n_air},
            temperature=AMBIENT_TEMPERATURE_K,
            pressure=pressure,
        )
        if Q >= 0.0:
            queue.append(carrier)
        else:
            queue.appendleft(carrier)


def _route_pocket(
    pocket: Pocket,
    node_id: str,
    junction_neighbors: dict[str, list[tuple[str, HydraulicEdge]]],
    transport_by_node: dict[str, list[tuple[str, HydraulicEdge]]],
    inventory_nodes: set[str],
    hub_nodes: set[str],
    arrivals: dict[str, list[Pocket]],
    hub_staging: dict[str, list[Pocket]],
    transport_staging: dict[str, list[Pocket]],
    hyd_state: HydraulicState,
    dt: float,
) -> None:
    """Route a pocket to its final destination, following JUNCTION edges.

    Traversal terminates when the pocket reaches:

    - An inventory node → appended to ``arrivals``.
    - A hub node → staged in ``hub_staging`` for merging.
    - A dead-end port (boundary component: FlowSource, PressureControl)
      → silently discarded (absorbed by the BC).

    Parameters
    ----------
    pocket:
        The pocket to route.
    node_id:
        The node at which the pocket has just arrived.
    junction_neighbors, inventory_nodes, hub_nodes:
        Pre-built indices from :func:`_build_indices`.
    arrivals, hub_staging:
        Output accumulators (modified in place).
    hyd_state:
        Used to determine JUNCTION flow direction at each hop.
    """
    current = node_id
    for _ in range(MAX_JUNCTION_HOPS):
        if current in inventory_nodes:
            arrivals[current].append(pocket)
            return
        if current in hub_nodes:
            hub_staging[current].append(pocket)
            return

        # Follow the JUNCTION edge whose flow points away from current.
        next_node: str | None = None
        for neighbor_id, edge in junction_neighbors.get(current, []):
            if is_hydraulically_closed(edge):
                continue
            Q = hyd_state.flows.get(edge.edge_id, 0.0)
            if edge.origin_node_id == current and Q > MIN_POCKET_VOLUME:
                next_node = neighbor_id
                break
            if edge.destination_node_id == current and Q < -MIN_POCKET_VOLUME:
                next_node = neighbor_id
                break

        if next_node is not None:
            current = next_node
            continue

        outgoing_dv = _outgoing_transport_dv(current, hyd_state, dt, transport_by_node)
        if outgoing_dv:
            _stage_transport_injections(pocket, outgoing_dv, transport_staging)
            return

        # Dead end: pocket absorbed by boundary component.
        return

    logger.warning(
        "Pocket routing exceeded {} JUNCTION hops from node '{}' - pocket discarded.",
        MAX_JUNCTION_HOPS,
        node_id,
    )


def _connects_to_inventory(
    node_id: str,
    graph: HydraulicGraph,
    junction_neighbors: dict[str, list[tuple[str, HydraulicEdge]]],
) -> bool:
    """Return True when *node_id* reaches inventory through open junctions."""
    if node_id in graph.inventory_nodes:
        return True

    queue: deque[tuple[str, int]] = deque([(node_id, 0)])
    seen = {node_id}
    while queue:
        current_node_id, depth = queue.popleft()
        if depth >= MAX_JUNCTION_HOPS:
            continue
        for neighbor_id, junction_edge in junction_neighbors.get(current_node_id, []):
            if is_hydraulically_closed(junction_edge):
                continue
            if neighbor_id in graph.inventory_nodes:
                return True
            if neighbor_id in seen:
                continue
            seen.add(neighbor_id)
            queue.append((neighbor_id, depth + 1))

    return False


def _process_hub(
    hub_id: str,
    staged: list[Pocket],
    hyd_state: HydraulicState,
    dt: float,
    junction_neighbors: dict[str, list[tuple[str, HydraulicEdge]]],
    transport_by_node: dict[str, list[tuple[str, HydraulicEdge]]],
    new_queues: dict[str, deque[Pocket]],
) -> None:
    """Merge pockets at a hub and distribute to outgoing transport edges.

    Algorithm:

    1. Merge all staged pockets by phase (via
       :func:`~chemunited_sim.transport.junction.merge_arriving_pockets`).
    2. Find outgoing TRANSPORT edges, which can be attached either directly
       to the hub itself (e.g. a rotary distribution valve's common port,
       which is simultaneously the hub node and an external tubing
       attachment point) or reachable from this hub via a JUNCTION edge to a
       neighboring port, where the TRANSPORT edge carries flow away from the
       port. A JUNCTION edge whose ``resistance_override`` marks it closed
       (an unselected valve position) is never treated as a redistribution
       path, even if the finite closed resistance leaves it a tiny nonzero
       solved flow.
    3. Distribute each merged pocket across outgoing edges proportionally to
       their displaced volume ``|Q|·dt``.
    4. Inject pocket fragments at the inflow end of each outgoing edge.
    """
    merged = merge_arriving_pockets(staged)
    if not merged:
        return

    # Outgoing transport edges keyed by edge_id → dV. Seed with any TRANSPORT
    # edge attached directly to the hub node itself (e.g. a distribution
    # valve's common port), then add edges reachable one JUNCTION hop away.
    outgoing_dv: dict[str, float] = dict(
        _outgoing_transport_dv(hub_id, hyd_state, dt, transport_by_node)
    )

    for port_id, junc_edge in junction_neighbors.get(hub_id, []):
        if is_hydraulically_closed(junc_edge):
            continue  # closed valve/BPR position - never a redistribution target

        Q_junc = hyd_state.flows.get(junc_edge.edge_id, 0.0)
        hub_to_port = (
            junc_edge.origin_node_id == hub_id and Q_junc > MIN_POCKET_VOLUME
        ) or (junc_edge.destination_node_id == hub_id and Q_junc < -MIN_POCKET_VOLUME)
        if not hub_to_port:
            continue

        for trans_id, trans_edge in transport_by_node.get(port_id, []):
            Q_trans = hyd_state.flows.get(trans_id, 0.0)
            away_from_port = (
                trans_edge.origin_node_id == port_id and Q_trans > MIN_POCKET_VOLUME
            ) or (
                trans_edge.destination_node_id == port_id
                and Q_trans < -MIN_POCKET_VOLUME
            )
            if away_from_port:
                outgoing_dv[trans_id] = (
                    outgoing_dv.get(trans_id, 0.0) + abs(Q_trans) * dt
                )
                break

    if not outgoing_dv:
        return

    total_out = sum(outgoing_dv.values())
    if total_out < MIN_POCKET_VOLUME:
        return

    for merged_pocket in merged:
        for trans_id, dV in outgoing_dv.items():
            frac = dV / total_out
            vol = merged_pocket.volume * frac
            if vol < MIN_POCKET_VOLUME:
                continue
            fragment = _scale_pocket(merged_pocket, frac)
            Q_trans = hyd_state.flows.get(trans_id, 0.0)
            if Q_trans >= 0:
                # Inflow at origin end → append to right
                new_queues[trans_id].append(fragment)
            else:
                # Inflow at destination end → appendleft to left
                new_queues[trans_id].appendleft(fragment)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TransportHeatExchangeEntry:
    """Wall heat-exchange parameters for one transport edge."""

    edge_id: str
    U: float
    diameter: float
    T_wall: float


def _pocket_thermal_mass(pocket: Pocket) -> float:
    """Return the tracked species thermal mass for a pocket in J/K."""
    total = 0.0
    phase = pocket.phase_kind
    phase_name = "liquid" if phase == PhaseKind.LIQUID else "gas"
    for species_id, moles in pocket.species_moles.items():
        if species_id not in COMPOUNDS:
            continue
        key = (species_id, phase)
        cp = _CP_CACHE.get(key)
        if cp is None:
            cp = COMPOUNDS[species_id].cp(phase_name).to_base_units().magnitude
            _CP_CACHE[key] = cp
        total += moles * cp
    return total


def _heat_pocket(pocket: Pocket, T_wall: float, rate_factor: float) -> Pocket:
    if abs(pocket.temperature - T_wall) <= 1.0e-12:
        return pocket

    c_thermal = _pocket_thermal_mass(pocket)
    if c_thermal <= 0.0:
        return pocket

    exponent = -(rate_factor * pocket.volume / c_thermal)
    temperature = T_wall + (pocket.temperature - T_wall) * math.exp(exponent)
    return Pocket(
        phase_kind=pocket.phase_kind,
        volume=pocket.volume,
        species_moles=dict(pocket.species_moles),
        temperature=temperature,
        pressure=pocket.pressure,
    )


def apply_transport_heat_exchange(
    state: TransportState,
    entries: list[TransportHeatExchangeEntry],
    dt: float,
) -> None:
    """Apply wall heat exchange to pockets currently inside transport edges.

    Each pocket is heated independently by a plug-flow UA model with
    cylindrical area ``A = (4 / diameter) * pocket.volume``.
    """
    for entry in entries:
        if entry.U <= 0.0 or entry.diameter <= 0.0:
            continue
        queue = state.edge_queues.get(entry.edge_id)
        if not queue:
            continue
        rate_factor = entry.U * (4.0 / entry.diameter) * dt
        state.edge_queues[entry.edge_id] = deque(
            _heat_pocket(pocket, entry.T_wall, rate_factor) for pocket in queue
        )


def advance(
    graph: HydraulicGraph,
    hyd_state: HydraulicState,
    transport_state: TransportState,
    dt: float,
) -> TransportResult:
    """Advance the transport state by one time step.

    The function performs two passes:

    **Pass 1 — TRANSPORT edges:**
    For each open transport edge, compute the displaced volume
    ``dV = |Q|·dt``, pop that volume worth of pockets from the exit end of
    the queue (splitting the boundary pocket if necessary), and route each
    exiting pocket to its destination:

    - Inventory node → ``arrivals[inv_node_id]``.
    - Hub node (junction centre) → staged for Pass 2.
    - Dead-end port (boundary component) → discarded.

    Any JUNCTION passthrough hops are followed in the same step.
    Edges that are closed (``resistance_override ≥ R_MAX_HYDRAULIC/2``) or
    have zero flow carry their queues forward unchanged.

    **Pass 2 — Hub merging:**
    For each hub that received staged pockets, merge by phase (ideal mixing),
    then distribute proportionally to the displaced volumes of outgoing
    transport edges.

    After both passes, pockets below
    :data:`~chemunited_sim.common.constant.MIN_POCKET_VOLUME` are discarded.

    Parameters
    ----------
    graph:
        Compiled hydraulic graph (static for this step).
    hyd_state:
        Pressures and signed flows from the hydraulic solve for this step.
    transport_state:
        FIFO queues from the previous step (or from
        :func:`~chemunited_sim.transport.initialiser.build_initial_state`).
    dt:
        Simulation time step in seconds.

    Returns
    -------
    TransportResult
        ``next_state`` — updated queues.
        ``arrivals``   — pockets that reached each inventory node this step.
        ``departures`` — volume (m³) that left the inventory-connected end of
                         each transport edge (one entry per edge where the
                         inflow end neighbours an inventory node).
    """
    junction_neighbors, transport_by_node = _build_indices(graph)
    inventory_nodes: set[str] = set(graph.inventory_nodes.keys())
    hub_nodes: set[str] = {n.node_id for n in graph.nodes.values() if n.is_hub}

    # Initialise new queues — copy existing; add empty deques for new edges.
    new_queues: dict[str, deque[Pocket]] = {}
    for eid, edge in graph.edges.items():
        if edge.role != InternalEdgeRole.TRANSPORT:
            continue
        existing = transport_state.edge_queues.get(eid)
        new_queues[eid] = deque(existing) if existing is not None else deque()

    arrivals: dict[str, list[Pocket]] = defaultdict(list)
    hub_staging: dict[str, list[Pocket]] = defaultdict(list)
    transport_staging: dict[str, list[Pocket]] = defaultdict(list)
    departures: dict[str, float] = {}

    # ------------------------------------------------------------------
    # Pass 1: TRANSPORT edge movement
    # ------------------------------------------------------------------
    for eid, edge in graph.edges.items():
        if edge.role != InternalEdgeRole.TRANSPORT:
            continue

        # Skip closed edges (R_MAX_HYDRAULIC means no flow)
        if is_hydraulically_closed(edge):
            continue

        Q = hyd_state.flows.get(eid, 0.0)
        if Q == 0.0:
            continue

        dV = abs(Q) * dt
        if dV < MIN_POCKET_VOLUME:
            continue

        # from_left: True = pop from left (destination end) when Q > 0.
        from_left = Q > 0
        exit_node_id = edge.destination_node_id if Q > 0 else edge.origin_node_id
        inflow_node_id = edge.origin_node_id if Q > 0 else edge.destination_node_id

        exiting = _pop_volume(new_queues[eid], dV, from_left)

        for pocket in exiting:
            _route_pocket(
                pocket,
                exit_node_id,
                junction_neighbors,
                transport_by_node,
                inventory_nodes,
                hub_nodes,
                arrivals,
                hub_staging,
                transport_staging,
                hyd_state,
                dt,
            )

        if _connects_to_inventory(inflow_node_id, graph, junction_neighbors):
            departures[eid] = dV

    _inject_staged_transport(new_queues, transport_staging, hyd_state)

    # ------------------------------------------------------------------
    # Pass 2: Hub merging and distribution
    # ------------------------------------------------------------------
    for hub_id, staged in hub_staging.items():
        _process_hub(
            hub_id,
            staged,
            hyd_state,
            dt,
            junction_neighbors,
            transport_by_node,
            new_queues,
        )

    # ------------------------------------------------------------------
    # Discard sub-threshold pocket fragments
    # ------------------------------------------------------------------
    for eid in new_queues:
        new_queues[eid] = deque(
            p for p in new_queues[eid] if p.volume >= MIN_POCKET_VOLUME
        )

    return TransportResult(
        next_state=TransportState(edge_queues=new_queues),
        arrivals=dict(arrivals),
        departures=departures,
    )


def inject(
    state: TransportState,
    emitted: dict[str, Pocket],
    hyd_state: HydraulicState,
    graph: HydraulicGraph | None = None,
) -> TransportState:
    """Inject inventory-emitted pockets into transport edge queues.

    Called by the worker after the inventory emit step.  Each emitted pocket
    is appended to the **inflow end** of the specified edge, determined by the
    flow direction in *hyd_state*:

    - ``Q ≥ 0``: inflow at the origin end → ``append`` (right).
    - ``Q < 0``: inflow at the destination end → ``appendleft`` (left).

    Parameters
    ----------
    state:
        The transport state to augment (a shallow copy is made internally).
    emitted:
        ``{edge_id: Pocket}`` — one pocket per edge to inject.  Provided by
        the inventory module, which resolves the edge from the port's access
        type (TOP → gas, BOTTOM → liquid).
    hyd_state:
        Flows from the most recent hydraulic solve, used to determine which
        end of the edge is the inflow end.
    graph:
        Optional compiled graph.  When provided, underfilled transport edges
        are padded with air carrier pockets to preserve the always-filled
        edge invariant.

    Returns
    -------
    TransportState
        New state with the emitted pockets inserted.
    """
    new_queues = {eid: deque(q) for eid, q in state.edge_queues.items()}

    for edge_id, pocket in emitted.items():
        if pocket.volume < MIN_POCKET_VOLUME:
            continue
        queue = new_queues.get(edge_id)
        if queue is None:
            continue
        Q = hyd_state.flows.get(edge_id, 0.0)
        if Q >= 0:
            queue.append(pocket)
        else:
            queue.appendleft(pocket)

    if graph is not None:
        _fill_carrier_deficits(graph, new_queues, hyd_state)

    return TransportState(edge_queues=new_queues)
