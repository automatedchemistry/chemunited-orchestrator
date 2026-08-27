"""Source-edge mapping for FlowSource boundary components.

``build_source_map`` creates a static lookup table (built once at simulation
startup) that identifies every TRANSPORT edge whose inflow end originates
from a FlowSource boundary node.  Used by ``emit_from_sources`` to create
species-carrying pockets each tick.  Infinite sources use their declared
template concentration; finite SyringePump sources deplete their runtime
inventory state.
"""

from __future__ import annotations

from dataclasses import dataclass

from chemunited_core.components import ComponentData, FlowSourceData
from chemunited_core.components.enums import InternalEdgeRole

from ..adapter.models import HydraulicGraph


@dataclass(frozen=True)
class SourceEdgeEntry:
    """Associates one TRANSPORT edge with the FlowSource component that feeds it.

    Attributes
    ----------
    comp:
        The live FlowSourceData component instance.
    source_node_id:
        The single boundary node the FlowSource compiles to,
        e.g. ``"liquidpump.1"``.
    inv_node_id:
        The inventory snapshot node for this component,
        e.g. ``"liquidpump.Inventory"``.
    """

    comp: FlowSourceData
    source_node_id: str
    inv_node_id: str


SourceMap = dict[str, SourceEdgeEntry]


def build_source_map(
    graph: HydraulicGraph,
    components: list[ComponentData],
) -> SourceMap:
    """Build the static edge → FlowSource lookup table.

    Iterates all TRANSPORT edges and checks whether their ``origin_node_id``
    matches the single boundary node produced by a FlowSource component
    (``"{comp_name}.1"``).

    Parameters
    ----------
    graph:
        The compiled hydraulic graph.
    components:
        All live component instances in the simulation domain.

    Returns
    -------
    SourceMap
        ``{edge_id: SourceEdgeEntry}`` for every TRANSPORT edge that
        originates at a FlowSource boundary node.
    """
    flow_sources: dict[str, FlowSourceData] = {
        c.name: c for c in components if isinstance(c, FlowSourceData)
    }

    source_map: SourceMap = {}
    for eid, edge in graph.edges.items():
        if edge.role != InternalEdgeRole.TRANSPORT:
            continue
        parts = edge.origin_node_id.rsplit(".", 1)
        if len(parts) != 2:
            continue
        comp_name, port_str = parts
        if comp_name not in flow_sources or port_str != "1":
            continue
        source_map[eid] = SourceEdgeEntry(
            comp=flow_sources[comp_name],
            source_node_id=edge.origin_node_id,
            inv_node_id=f"{comp_name}.Inventory",
        )

    return source_map
