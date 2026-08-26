"""Port-access mapping for the inventory module.

``build_port_map`` creates a static lookup table (built once at simulation
startup) that resolves, for every transport edge whose inflow end borders a
vessel, which inventory node it drains from and whether that port prefers TOP
(gas side) or BOTTOM (liquid side) emission.

Valve switches change ``HydraulicEdge.resistance_override`` in-place and do
not rebuild the graph, so this map remains valid for the entire simulation run.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from chemunited_core.components import ComponentData, FlowSourceData
from chemunited_core.components.enums import InternalEdgeRole, PortAccess

from ..adapter.models import HydraulicEdge, HydraulicGraph
from ..common.constant import MAX_JUNCTION_HOPS
from ..common.edges import is_hydraulically_closed


@dataclass(frozen=True)
class EdgePortAccess:
    """Associates one transport edge with the inventory node and phase it drains.

    Attributes
    ----------
    inv_node_id:
        The inventory node this edge draws from,
        e.g. ``"vessel1.Inventory"``.
    access:
        ``PortAccess.TOP`` → gas phase preferred.
        ``PortAccess.BOTTOM`` → liquid phase preferred.
    """

    inv_node_id: str
    access: PortAccess


def _is_open_junction(edge: HydraulicEdge) -> bool:
    return edge.role == InternalEdgeRole.JUNCTION and not is_hydraulically_closed(edge)


def _junction_neighbors(graph: HydraulicGraph) -> dict[str, list[str]]:
    neighbors: dict[str, list[str]] = {}
    for edge in graph.edges.values():
        if not _is_open_junction(edge):
            continue
        neighbors.setdefault(edge.origin_node_id, []).append(edge.destination_node_id)
        neighbors.setdefault(edge.destination_node_id, []).append(edge.origin_node_id)
    return neighbors


def _nearest_inventory_port(
    start_node_id: str,
    port_to_inv: dict[str, str],
    neighbors: dict[str, list[str]],
) -> tuple[str, str] | None:
    queue: deque[tuple[str, int]] = deque([(start_node_id, 0)])
    seen = {start_node_id}

    while queue:
        node_id, depth = queue.popleft()
        inv_node_id = port_to_inv.get(node_id)
        if inv_node_id is not None:
            return node_id, inv_node_id
        if depth >= MAX_JUNCTION_HOPS:
            continue
        for neighbor_id in neighbors.get(node_id, []):
            if neighbor_id in seen:
                continue
            seen.add(neighbor_id)
            queue.append((neighbor_id, depth + 1))

    return None


# Mapping from transport edge_id to its port-access metadata.
PortAccessMap = dict[str, EdgePortAccess]


def build_port_map(
    graph: HydraulicGraph,
    components: list[ComponentData],
) -> PortAccessMap:
    """Build the static edge → port-access lookup table.

    The function performs three steps:

    1. Build ``comp_by_name`` from the component list for O(1) lookups.
    2. Identify vessel port nodes that connect to inventory nodes via
       JUNCTION edges (``port_node_id → inv_node_id``).
    3. For each TRANSPORT edge, check both endpoints; if either is a vessel
       port, record the inventory node and ``Port.access`` value.

    Parameters
    ----------
    graph:
        The compiled hydraulic graph.  Only the edge dict is read.
    components:
        All component instances in the simulation domain.  Used to look up
        ``Port.access`` for each vessel port node, since ``HydraulicNode``
        does not carry access metadata.

    Returns
    -------
    PortAccessMap
        ``{edge_id: EdgePortAccess}`` for every transport edge whose inflow
        end neighbours a vessel inventory node.
    """
    comp_by_name: dict[str, ComponentData] = {c.name: c for c in components}
    source_names = {c.name for c in components if isinstance(c, FlowSourceData)}

    # Step 1: port_node_id → inv_node_id from JUNCTION edges
    port_to_inv: dict[str, str] = {}
    for edge in graph.edges.values():
        if edge.role != InternalEdgeRole.JUNCTION:
            continue
        if edge.destination_node_id in graph.inventory_nodes:
            port_to_inv[edge.origin_node_id] = edge.destination_node_id
        elif edge.origin_node_id in graph.inventory_nodes:
            port_to_inv[edge.destination_node_id] = edge.origin_node_id

    # Step 2: helper to resolve PortAccess for a port node
    def _get_access(port_node_id: str) -> PortAccess | None:
        # port_node_id format: "component_name.port_number"
        parts = port_node_id.rsplit(".", 1)
        if len(parts) != 2:
            return None
        comp_name, port_num_str = parts
        try:
            port_num = int(port_num_str)
        except ValueError:
            return None
        comp = comp_by_name.get(comp_name)
        if comp is None:
            return None
        port = getattr(comp, "ports_by_number", {}).get(port_num)
        if port is None:
            return None
        return getattr(port, "access", None)

    # Step 3: build PortAccessMap from TRANSPORT edges. Direct vessel
    # endpoints still resolve immediately; autosampler paths may resolve
    # through currently open JUNCTION edges.
    neighbors = _junction_neighbors(graph)
    port_map: PortAccessMap = {}
    for eid, edge in graph.edges.items():
        if edge.role != InternalEdgeRole.TRANSPORT:
            continue
        for node_id in (edge.origin_node_id, edge.destination_node_id):
            resolved = _nearest_inventory_port(node_id, port_to_inv, neighbors)
            if resolved is None:
                continue
            port_node_id, inv_node_id = resolved
            comp_name = port_node_id.rsplit(".", 1)[0]
            if comp_name in source_names:
                continue
            access = _get_access(port_node_id)
            if access is not None:
                port_map[eid] = EdgePortAccess(inv_node_id=inv_node_id, access=access)
                break  # each edge has at most one active inventory source

    return port_map
