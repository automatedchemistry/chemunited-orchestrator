"""Adapter module - compiles ComponentData + EdgeData into a HydraulicGraph.

Public interface:
    compile_graph(components, edges) -> HydraulicGraph
    resync_component(graph, comp) -> None
    propagate_power_links(provider, graph, components_by_name, cache) -> None
"""

from .graph import compile_graph, propagate_power_links, resync_component
from .models import HydraulicEdge, HydraulicGraph, HydraulicNode

__all__ = [
    "compile_graph",
    "resync_component",
    "propagate_power_links",
    "HydraulicNode",
    "HydraulicEdge",
    "HydraulicGraph",
]
