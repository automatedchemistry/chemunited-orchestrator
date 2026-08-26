"""Per-component-type compilers that translate core ComponentData objects into
hydraulic graph primitives (HydraulicNode / HydraulicEdge).

Each compiler function accepts one typed component and returns a
``(nodes, edges)`` tuple.  Inventory nodes are NOT returned here; they are
handled by :func:`~chemunited_sim.adapter.graph.compile_graph` after dispatch.

Filtering rules applied in every compiler
------------------------------------------
- Ports where ``port.category != ConnectionType.HYDRAULIC`` are skipped.
- Ports where ``port.closure == PortClosure.CAPPED`` are skipped.
- Any internal edge whose endpoint port was skipped is also skipped.
"""

from __future__ import annotations

from typing import Callable

from chemunited_core.common.enums import ConnectionType
from chemunited_core.components import (
    ComponentData,
    FlowSourceData,
    JunctionData,
    PlugFlowComponentData,
    PressureControlData,
    ValveComponentData,
    VesselComponentData,
)
from chemunited_core.components.enums import InternalEdgeRole, PortClosure
from chemunited_core.figure_registry import Gantry3DData, VialData
from loguru import logger

from .models import HydraulicEdge, HydraulicNode

# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------


def _is_hydraulic_active(port, comp=None) -> bool:  # type: ignore[no-untyped-def]
    """Return ``True`` if *port* should become a hydraulic node.

    Standard hydraulic ports are included. Gantry/vial MOVEMENT ports are
    also included so autosampler tray contacts can participate in hydraulics
    without making every MOVEMENT edge a fluid path.
    """
    if port.closure == PortClosure.CAPPED:
        return False
    if port.category == ConnectionType.HYDRAULIC:
        return True
    return port.category == ConnectionType.MOVEMENT and isinstance(
        comp, (Gantry3DData, VialData)
    )


def _is_hub_port(port, port_number: int | str, comp) -> bool:  # type: ignore[no-untyped-def]
    """Return True when a port should stage and route transport pockets."""
    return bool(getattr(port, "is_hub", False)) or (
        isinstance(comp, ValveComponentData) and port_number == 0
    )


# ---------------------------------------------------------------------------
# PlugFlowComponentData
# ---------------------------------------------------------------------------


def compile_plugflow(
    comp: PlugFlowComponentData,
) -> tuple[list[HydraulicNode], list[HydraulicEdge]]:
    """Compile a plug-flow tube segment into one transport edge.

    A plug-flow component has exactly two hydraulic ports (1 and 2) connected
    by a single internal transport edge whose geometry determines resistance
    via Hagen–Poiseuille.

    Parameters
    ----------
    comp:
        The source plug-flow component.

    Returns
    -------
    tuple[list[HydraulicNode], list[HydraulicEdge]]
        Nodes for any non-filtered ports and at most one transport edge.
    """
    nodes: list[HydraulicNode] = []
    valid_port_numbers: set[int | str] = set()

    for port_number, port in comp.ports_by_number.items():
        if not _is_hydraulic_active(port, comp):
            continue
        nodes.append(
            HydraulicNode(
                node_id=f"{comp.name}.{port_number}",
                boundary=port.boundary,
                is_hub=False,
                component=comp.name,
            )
        )
        valid_port_numbers.add(port_number)

    edges: list[HydraulicEdge] = []
    if 1 in valid_port_numbers and 2 in valid_port_numbers:
        edge = comp.internal_edges[(1, 2)]
        edges.append(
            HydraulicEdge(
                edge_id=f"{comp.name}.1.2",
                origin_node_id=f"{comp.name}.1",
                destination_node_id=f"{comp.name}.2",
                length=edge.length,
                diameter=edge.diameter,
                role=InternalEdgeRole.TRANSPORT,
                resistance_override=edge.resistance_override,
                component=comp.name,
                is_external=False,
            )
        )

    return nodes, edges


# ---------------------------------------------------------------------------
# VesselComponentData
# ---------------------------------------------------------------------------


def compile_vessel(
    comp: VesselComponentData,
) -> tuple[list[HydraulicNode], list[HydraulicEdge]]:
    """Compile a vessel (tank / reservoir) into port nodes plus an inventory hub.

    The vessel's internal inventory node acts as the common pressure point for
    all hydraulic ports.  Each port is connected to the inventory node by a
    short junction edge.  The heat port (``ConnectionType.HEAT``) is skipped
    by the category filter automatically.

    Parameters
    ----------
    comp:
        The source vessel component.

    Returns
    -------
    tuple[list[HydraulicNode], list[HydraulicEdge]]
        Port nodes, the inventory node, and junction edges from each port to
        the inventory.
    """
    nodes: list[HydraulicNode] = []
    valid_port_numbers: set[int | str] = set()

    for port_number, port in comp.ports_by_number.items():
        if not _is_hydraulic_active(port, comp):
            continue
        nodes.append(
            HydraulicNode(
                node_id=f"{comp.name}.{port_number}",
                boundary=port.boundary,
                is_hub=False,
                component=comp.name,
            )
        )
        valid_port_numbers.add(port_number)

    for inventory_key in comp.internal_inventories:
        nodes.append(
            HydraulicNode(
                node_id=f"{comp.name}.{inventory_key}",
                boundary=None,
                is_hub=False,
                component=comp.name,
            )
        )

    edges: list[HydraulicEdge] = []
    for (port_number, dest), edge in comp.internal_edges.items():
        if dest not in comp.internal_inventories:
            continue
        if port_number not in valid_port_numbers:
            continue
        edges.append(
            HydraulicEdge(
                edge_id=f"{comp.name}.{port_number}.{dest}",
                origin_node_id=f"{comp.name}.{port_number}",
                destination_node_id=f"{comp.name}.{dest}",
                length=edge.length,
                diameter=edge.diameter,
                role=InternalEdgeRole.JUNCTION,
                resistance_override=edge.resistance_override,
                component=comp.name,
                is_external=False,
            )
        )

    return nodes, edges


# ---------------------------------------------------------------------------
# ValveComponentData
# ---------------------------------------------------------------------------


def compile_valve(
    comp: ValveComponentData,
) -> tuple[list[HydraulicNode], list[HydraulicEdge]]:
    """Compile a valve into junction edges between its hydraulic ports.

    Valve channels are modelled as lossless junctions whose resistance is
    controlled entirely by ``resistance_override``: ``None`` means open
    (R = 0 in the JUNCTION role), ``R_MAX_HYDRAULIC`` means closed.

    Parameters
    ----------
    comp:
        The source valve component.

    Returns
    -------
    tuple[list[HydraulicNode], list[HydraulicEdge]]
        Nodes for active ports and junction edges for open channels.
    """
    nodes: list[HydraulicNode] = []
    valid_port_numbers: set[int | str] = set()

    for port_number, port in comp.ports_by_number.items():
        if not _is_hydraulic_active(port, comp):
            continue
        nodes.append(
            HydraulicNode(
                node_id=f"{comp.name}.{port_number}",
                boundary=port.boundary,
                is_hub=_is_hub_port(port, port_number, comp),
                component=comp.name,
            )
        )
        valid_port_numbers.add(port_number)

    edges: list[HydraulicEdge] = []
    for (origin, dest), edge in comp.internal_edges.items():
        if origin not in valid_port_numbers or dest not in valid_port_numbers:
            continue
        edges.append(
            HydraulicEdge(
                edge_id=f"{comp.name}.{origin}.{dest}",
                origin_node_id=f"{comp.name}.{origin}",
                destination_node_id=f"{comp.name}.{dest}",
                length=edge.length,
                diameter=edge.diameter,
                role=InternalEdgeRole.JUNCTION,
                resistance_override=edge.resistance_override,
                component=comp.name,
                is_external=False,
            )
        )

    return nodes, edges


# ---------------------------------------------------------------------------
# FlowSourceData
# ---------------------------------------------------------------------------


def compile_flow_source(
    comp: FlowSourceData,
) -> tuple[list[HydraulicNode], list[HydraulicEdge]]:
    """Compile a flow source into a passive port node + Inventory node + nozzle edge.

    Port 1 is passive (boundary=None) — it is solved by the network.
    The Inventory node carries the FLOW BC that drives fluid through the nozzle.
    The nozzle (InternalEdge) starts closed; resync_component() propagates its
    resistance_override each tick after sync_internal_state() opens or closes it.

    Parameters
    ----------
    comp:
        The source flow-source component.

    Returns
    -------
    tuple[list[HydraulicNode], list[HydraulicEdge]]
        Two nodes (port + inventory) and one internal nozzle edge.
    """
    nodes: list[HydraulicNode] = []
    port = comp.ports_by_number.get(1)

    if port is None:
        return nodes, []

    if not _is_hydraulic_active(port, comp):
        logger.warning(
            "compile_flow_source: component '{}' port 1 is CAPPED - "
            "this flow source is degenerate and will have no effect on the network.",
            comp.name,
        )
        return nodes, []

    # Port 1 — passive junction node, no boundary condition
    nodes.append(
        HydraulicNode(
            node_id=f"{comp.name}.1",
            boundary=port.boundary,  # None
            is_hub=False,
            component=comp.name,
        )
    )

    # Inventory node — FLOW BC drives fluid through the nozzle
    nodes.append(
        HydraulicNode(
            node_id=f"{comp.name}.Inventory",
            boundary=comp._inventory_bc,
            is_hub=False,
            component=comp.name,
        )
    )

    # Nozzle edge — JUNCTION, starts closed (resistance_override = R_MAX)
    nozzle = comp.internal_edges[(1, "Inventory")]
    edges: list[HydraulicEdge] = [
        HydraulicEdge(
            edge_id=f"{comp.name}.1.Inventory",
            origin_node_id=f"{comp.name}.1",
            destination_node_id=f"{comp.name}.Inventory",
            length=0.0,
            diameter=0.0,
            role=InternalEdgeRole.JUNCTION,
            resistance_override=nozzle.resistance_override,
            component=comp.name,
            is_external=False,
        )
    ]
    return nodes, edges


# ---------------------------------------------------------------------------
# PressureControlData
# ---------------------------------------------------------------------------


def compile_pressure_control(
    comp: PressureControlData,
) -> tuple[list[HydraulicNode], list[HydraulicEdge]]:
    """Compile a pressure-control boundary into a single node with no internal edges.

    Pressure-control components impose a fixed pressure at port 1 via their
    boundary condition.  They contribute no internal edges to the graph.

    Parameters
    ----------
    comp:
        The source pressure-control component.

    Returns
    -------
    tuple[list[HydraulicNode], list[HydraulicEdge]]
        At most one node; no edges.
    """
    nodes: list[HydraulicNode] = []
    port = comp.ports_by_number.get(1)

    if port is None:
        return nodes, []

    if not _is_hydraulic_active(port, comp):
        return nodes, []

    nodes.append(
        HydraulicNode(
            node_id=f"{comp.name}.1",
            boundary=port.boundary,
            is_hub=False,
            component=comp.name,
        )
    )
    return nodes, []


# ---------------------------------------------------------------------------
# JunctionData
# ---------------------------------------------------------------------------


def compile_junction(
    comp: JunctionData,
) -> tuple[list[HydraulicNode], list[HydraulicEdge]]:
    """Compile a fluidic junction (T-piece, manifold, etc.) into a star topology.

    A junction has a synthetic hub port (port 0) that is never filtered — it is
    the common pressure node to which all external ports connect.  External
    ports 1..N are subject to the standard hydraulic-active filter.

    Parameters
    ----------
    comp:
        The source junction component.

    Returns
    -------
    tuple[list[HydraulicNode], list[HydraulicEdge]]
        Hub node, any active external-port nodes, and junction edges from each
        active external port to the hub.
    """
    # Hub node — always emitted, never filtered
    hub_node = HydraulicNode(
        node_id=f"{comp.name}.0",
        boundary=None,
        is_hub=True,
        component=comp.name,
    )
    nodes: list[HydraulicNode] = [hub_node]
    valid_port_numbers: set[int | str] = set()

    for port_number, port in comp.ports_by_number.items():
        if port_number == 0:
            continue  # hub is handled above
        if not _is_hydraulic_active(port, comp):
            continue
        nodes.append(
            HydraulicNode(
                node_id=f"{comp.name}.{port_number}",
                boundary=port.boundary,
                is_hub=False,
                component=comp.name,
            )
        )
        valid_port_numbers.add(port_number)

    edges: list[HydraulicEdge] = []
    for (ext_port, hub), edge in comp.internal_edges.items():
        if hub != 0:
            continue
        if ext_port not in valid_port_numbers:
            continue
        edges.append(
            HydraulicEdge(
                edge_id=f"{comp.name}.{ext_port}.0",
                origin_node_id=f"{comp.name}.{ext_port}",
                destination_node_id=f"{comp.name}.0",
                length=edge.length,
                diameter=edge.diameter,
                role=InternalEdgeRole.JUNCTION,
                resistance_override=edge.resistance_override,
                component=comp.name,
                is_external=False,
            )
        )

    return nodes, edges


# ---------------------------------------------------------------------------
# Generic fallback
# ---------------------------------------------------------------------------


def compile_component(
    comp: ComponentData,
) -> tuple[list[HydraulicNode], list[HydraulicEdge]]:
    """Generic fallback compiler for any ComponentData subclass.

    Iterates ``comp.ports_by_number`` and ``comp.internal_edges`` applying the
    standard hydraulic-active filter.  Supports both integer–integer and
    integer–``"Inventory"`` edge keys.

    Use this compiler when no specific compiler exists for a component type.
    It degrades gracefully: unrecognised port types are simply skipped.

    Parameters
    ----------
    comp:
        Any ComponentData subclass not handled by a specific compiler.

    Returns
    -------
    tuple[list[HydraulicNode], list[HydraulicEdge]]
        Nodes for all active hydraulic ports and edges whose both endpoints
        are active (or whose destination is ``"Inventory"`` and the origin is
        active).
    """
    nodes: list[HydraulicNode] = []
    valid_node_ids: set[str] = set()

    for port_number, port in comp.ports_by_number.items():
        if not _is_hydraulic_active(port, comp):
            continue
        node_id = f"{comp.name}.{port_number}"
        nodes.append(
            HydraulicNode(
                node_id=node_id,
                boundary=port.boundary,
                is_hub=_is_hub_port(port, port_number, comp),
                component=comp.name,
            )
        )
        valid_node_ids.add(node_id)

    edges: list[HydraulicEdge] = []
    for (origin, dest), edge in comp.internal_edges.items():
        origin_node_id = f"{comp.name}.{origin}"
        if origin_node_id not in valid_node_ids:
            continue

        if dest == "Inventory":
            destination_node_id = f"{comp.name}.Inventory"
        else:
            destination_node_id = f"{comp.name}.{dest}"
            if destination_node_id not in valid_node_ids:
                continue

        edges.append(
            HydraulicEdge(
                edge_id=f"{comp.name}.{origin}.{dest}",
                origin_node_id=origin_node_id,
                destination_node_id=destination_node_id,
                length=edge.length,
                diameter=edge.diameter,
                role=edge.role,
                resistance_override=edge.resistance_override,
                component=comp.name,
                is_external=False,
                forced_flow=edge.forced_flow_override,
            )
        )

    return nodes, edges


# ---------------------------------------------------------------------------
# Dispatch registry
# ---------------------------------------------------------------------------

# Mapping from ComponentData subtype to its dedicated compiler function.
# Falls back to compile_component for any type not listed here.
# Dispatch uses exact type(comp) -- not isinstance/MRO.
_COMPILERS: dict[
    type, Callable[..., tuple[list[HydraulicNode], list[HydraulicEdge]]]
] = {
    PlugFlowComponentData: compile_plugflow,
    VesselComponentData: compile_vessel,
    ValveComponentData: compile_valve,
    FlowSourceData: compile_flow_source,
    PressureControlData: compile_pressure_control,
    JunctionData: compile_junction,
}
