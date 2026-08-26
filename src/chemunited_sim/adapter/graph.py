"""Top-level graph compiler for the adapter layer.

:func:`compile_graph` is the single entry point that consumes a flat list of
``ComponentData`` objects and ``EdgeData`` connections and produces a fully
resolved :class:`~chemunited_sim.adapter.models.HydraulicGraph` ready for the
simulation kernel.
"""

from __future__ import annotations

import copy
from dataclasses import replace

from chemunited_core.common.enums import ConnectionType
from chemunited_core.components import ComponentData, NeutralComponentData
from chemunited_core.components.enums import InternalEdgeRole
from chemunited_core.components.internals import InventoryNode
from chemunited_core.components.plugflow import PlugFlowComponentData
from chemunited_core.connections.edge import EdgeData
from chemunited_core.figure_registry import (
    Gantry3DData,
    MultiChannelData,
    MultiChannelRelayData,
    VialData,
)
from loguru import logger

from .compilers import _COMPILERS, compile_component
from .models import HeatLink, HydraulicEdge, HydraulicGraph, HydraulicNode, PowerLink


def resync_component(graph: HydraulicGraph, comp: ComponentData) -> None:
    """Propagate mutable component state into HydraulicGraph.

    Called immediately after ComponentData.apply(). Topology is never changed;
    edge resistance overrides, forced-flow overrides, and port boundaries are
    refreshed in-place.
    """
    for port_number, port in comp.ports_by_number.items():
        node_id = f"{comp.name}.{port_number}"
        node = graph.nodes.get(node_id)
        if node is not None:
            graph.nodes[node_id] = replace(node, boundary=port.boundary)

    for (origin, dest), internal_edge in comp.internal_edges.items():
        edge_id = f"{comp.name}.{origin}.{dest}"
        hydraulic_edge = graph.edges.get(edge_id)
        if hydraulic_edge is not None:
            hydraulic_edge.resistance_override = internal_edge.resistance_override
            hydraulic_edge.forced_flow = internal_edge.forced_flow_override


def propagate_power_links(
    provider: ComponentData,
    graph: HydraulicGraph,
    components_by_name: dict[str, ComponentData],
    power_state_cache: dict[tuple[str, int], bool],
) -> None:
    """Energize/de-energize every target wired to ``provider``'s channels.

    Call immediately after ``provider.apply(...)`` + ``resync_component(graph,
    provider)`` for any command applied to a component. No-ops for any
    component that is not a :class:`MultiChannelRelayData`. Walks
    ``graph.power_links`` for links whose ``provider_component`` matches,
    compares each channel's new ``active`` state against ``power_state_cache``,
    and only re-applies ``"power-on"``/``"power-off"`` (+ resync) to the
    linked target(s) on an actual transition -- so redundant commands (e.g.
    ``"power-on"`` sent twice for an already-ON channel) do not re-invoke
    ``target.apply()`` and risk re-triggering side effects such as a
    scheduled follow-up event.
    """
    if not isinstance(provider, MultiChannelRelayData):
        return
    for link in graph.power_links:
        if link.provider_component != provider.name:
            continue
        if not isinstance(link.provider_port, int):
            continue
        index = link.provider_port - 1
        if not (0 <= index < len(provider.active)):
            continue
        new_state = bool(provider.active[index])
        cache_key = (provider.name, link.provider_port)
        if power_state_cache.get(cache_key) == new_state:
            continue
        power_state_cache[cache_key] = new_state
        target = components_by_name.get(link.target_component)
        if target is None:
            continue
        target.apply("power-on" if new_state else "power-off")
        resync_component(graph, target)


def _port_category(
    comp: ComponentData, port_number: int | str
) -> ConnectionType | None:
    if not isinstance(port_number, int):
        return None
    port = comp.ports_by_number.get(port_number)
    return None if port is None else port.category


def _is_heat_provider(comp: ComponentData) -> bool:
    return isinstance(comp, NeutralComponentData)


def _is_heat_target(comp: ComponentData) -> bool:
    return bool(getattr(comp, "heat_exchange", False)) and not _is_heat_provider(comp)


def _is_electronic_provider(comp: ComponentData) -> bool:
    return isinstance(comp, MultiChannelRelayData)


def _is_electronic_target(comp: ComponentData) -> bool:
    return not isinstance(comp, MultiChannelData)


def _is_autosampler_contact_edge(
    edge_data: EdgeData, components_by_name: dict[str, ComponentData]
) -> bool:
    if edge_data.classification != ConnectionType.MOVEMENT:
        return False

    origin = components_by_name.get(edge_data.origin)
    destination = components_by_name.get(edge_data.destination)
    return (isinstance(origin, Gantry3DData) and isinstance(destination, VialData)) or (
        isinstance(origin, VialData) and isinstance(destination, Gantry3DData)
    )


def _compile_heat_link(
    edge_data: EdgeData,
    components_by_name: dict[str, ComponentData],
    linked_targets: set[str],
) -> HeatLink:
    endpoints = [
        (edge_data.origin, edge_data.origin_port),
        (edge_data.destination, edge_data.destination_port),
    ]
    resolved: list[tuple[ComponentData, int | str]] = []

    for comp_name, port_number in endpoints:
        comp = components_by_name.get(comp_name)
        if comp is None:
            raise ValueError(
                f"HEAT edge '{edge_data.name}' references unknown component "
                f"'{comp_name}'"
            )
        if _port_category(comp, port_number) != ConnectionType.HEAT:
            raise ValueError(
                f"HEAT edge '{edge_data.name}' endpoint "
                f"'{comp_name}.{port_number}' is not a HEAT port"
            )
        resolved.append((comp, port_number))

    providers = [(comp, port) for comp, port in resolved if _is_heat_provider(comp)]
    targets = [(comp, port) for comp, port in resolved if _is_heat_target(comp)]

    if len(providers) != 1 or len(targets) != 1:
        names = ", ".join(f"{comp.name}.{port}" for comp, port in resolved)
        raise ValueError(
            f"HEAT edge '{edge_data.name}' must connect exactly one thermal "
            f"controller to one heat-enabled target; got {names}"
        )

    provider, provider_port = providers[0]
    target, target_port = targets[0]
    if target.name in linked_targets:
        raise ValueError(
            f"Component '{target.name}' has multiple HEAT controllers; only one "
            "thermal provider per target is supported"
        )
    linked_targets.add(target.name)

    return HeatLink(
        provider_component=provider.name,
        provider_port=provider_port,
        target_component=target.name,
        target_port=target_port,
    )


def _compile_power_link(
    edge_data: EdgeData,
    components_by_name: dict[str, ComponentData],
    linked_targets: set[str],
) -> PowerLink:
    endpoints = [
        (edge_data.origin, edge_data.origin_port),
        (edge_data.destination, edge_data.destination_port),
    ]
    resolved: list[tuple[ComponentData, int | str]] = []

    for comp_name, port_number in endpoints:
        comp = components_by_name.get(comp_name)
        if comp is None:
            raise ValueError(
                f"ELECTRONIC edge '{edge_data.name}' references unknown component "
                f"'{comp_name}'"
            )
        if _port_category(comp, port_number) != ConnectionType.ELECTRONIC:
            raise ValueError(
                f"ELECTRONIC edge '{edge_data.name}' endpoint "
                f"'{comp_name}.{port_number}' is not an ELECTRONIC port"
            )
        resolved.append((comp, port_number))

    providers = [
        (comp, port) for comp, port in resolved if _is_electronic_provider(comp)
    ]
    targets = [(comp, port) for comp, port in resolved if _is_electronic_target(comp)]

    if len(providers) != 1 or len(targets) != 1:
        names = ", ".join(f"{comp.name}.{port}" for comp, port in resolved)
        raise ValueError(
            f"ELECTRONIC edge '{edge_data.name}' must connect exactly one relay "
            f"channel to one energizable target; got {names}"
        )

    provider, provider_port = providers[0]
    target, target_port = targets[0]
    if target.name in linked_targets:
        raise ValueError(
            f"Component '{target.name}' has multiple electronic providers; only "
            "one relay channel per target is supported"
        )
    linked_targets.add(target.name)

    return PowerLink(
        provider_component=provider.name,
        provider_port=provider_port,
        target_component=target.name,
        target_port=target_port,
    )


def compile_graph(
    components: list[ComponentData],
    edges: list[EdgeData],
) -> HydraulicGraph:
    """Compile a component-and-connection description into a HydraulicGraph.

    The function performs three passes:

    1. **Component pass** — dispatches each component to its dedicated
       compiler (or the generic fallback), collects nodes and internal edges,
       takes a deep-copy snapshot of any ``internal_inventory``, and registers
       BPR edge IDs.

    2. **External-edge pass** — iterates ``EdgeData`` connections, skips
       non-HYDRAULIC edges silently, logs warnings for edges whose
       endpoint nodes are absent (e.g. CAPPED ports), and inserts
       ``TRANSPORT`` edges with geometry taken from ``EdgeData``.

    3. **Assembly** — wraps everything in a :class:`HydraulicGraph` and
       returns it.

    Parameters
    ----------
    components:
        All component instances that belong to the simulation domain.
        Component names must be unique; a ``ValueError`` is raised otherwise.
    edges:
        All directed connections between component ports.  Non-hydraulic edges
        are silently ignored.  Edges whose endpoint nodes are missing log a
        warning and are skipped.

    Returns
    -------
    HydraulicGraph
        A fully populated graph containing nodes, internal and external edges,
        inventory snapshots, and the BPR edge registry.

    Raises
    ------
    ValueError
        If two components share the same name, or if two external edges share
        the same ``EdgeData.name``.

    Notes
    -----
    - All length values are in metres (m).
    - All diameter values are in metres (m).
    - Resistance values are in Pa·s/m³.
    """
    seen_names: set[str] = set()
    all_nodes: dict[str, HydraulicNode] = {}
    all_edges: dict[str, HydraulicEdge] = {}
    all_inventory: dict[str, InventoryNode] = {}
    components_by_name: dict[str, ComponentData] = {}

    # ------------------------------------------------------------------
    # Pass 1: component compilers
    # ------------------------------------------------------------------
    for comp in components:
        if comp.name in seen_names:
            raise ValueError(f"Duplicate component name '{comp.name}'")
        seen_names.add(comp.name)
        components_by_name[comp.name] = comp

        comp.apply_air_defaults()

        compiler = next(
            (_COMPILERS[cls] for cls in type(comp).mro() if cls in _COMPILERS),
            compile_component,
        )
        nodes, comp_edges = compiler(comp)

        for node in nodes:
            all_nodes[node.node_id] = node
        for edge in comp_edges:
            if (
                isinstance(comp, PlugFlowComponentData)
                and edge.role == InternalEdgeRole.TRANSPORT
            ):
                edge.content = list(comp.content)
            all_edges[edge.edge_id] = edge

        # Inventory snapshots (deep copy to decouple from live component state)
        for inventory_key, inventory in comp.internal_inventories.items():
            inv_id = f"{comp.name}.{inventory_key}"
            all_inventory[inv_id] = copy.deepcopy(inventory)

    # ------------------------------------------------------------------
    # Pass 2: external edges
    # ------------------------------------------------------------------
    for edge_data in edges:
        is_autosampler_contact = _is_autosampler_contact_edge(
            edge_data, components_by_name
        )
        if (
            edge_data.classification != ConnectionType.HYDRAULIC
            and not is_autosampler_contact
        ):
            continue  # silently skip unrelated non-HYDRAULIC edges

        origin_node_id = f"{edge_data.origin}.{edge_data.origin_port}"
        dest_node_id = f"{edge_data.destination}.{edge_data.destination_port}"

        if origin_node_id not in all_nodes:
            logger.warning(
                "compile_graph: skipping edge '{}' - origin node '{}' not in graph "
                "(port may be CAPPED or component missing).",
                edge_data.name,
                origin_node_id,
            )
            continue
        if dest_node_id not in all_nodes:
            logger.warning(
                "compile_graph: skipping edge '{}' - destination node '{}' not in "
                "graph "
                "(port may be CAPPED or component missing).",
                edge_data.name,
                dest_node_id,
            )
            continue

        if edge_data.name in all_edges:
            raise ValueError(f"Duplicate external edge ID '{edge_data.name}'")

        edge_data.apply_air_defaults()

        all_edges[edge_data.name] = HydraulicEdge(
            edge_id=edge_data.name,
            origin_node_id=origin_node_id,
            destination_node_id=dest_node_id,
            length=0.0 if is_autosampler_contact else edge_data.length_value,
            diameter=0.0 if is_autosampler_contact else edge_data.diameter_value,
            role=(
                InternalEdgeRole.JUNCTION
                if is_autosampler_contact
                else InternalEdgeRole.TRANSPORT
            ),
            resistance_override=None,
            component=None,
            is_external=True,
            content=list(edge_data.content),
        )

    # ------------------------------------------------------------------
    # Pass 3: heat links
    # ------------------------------------------------------------------
    heat_links: list[HeatLink] = []
    linked_heat_targets: set[str] = set()
    for edge_data in edges:
        if edge_data.classification != ConnectionType.HEAT:
            continue
        heat_links.append(
            _compile_heat_link(edge_data, components_by_name, linked_heat_targets)
        )

    # ------------------------------------------------------------------
    # Pass 4: power links
    # ------------------------------------------------------------------
    power_links: list[PowerLink] = []
    linked_power_targets: set[str] = set()
    for edge_data in edges:
        if edge_data.classification != ConnectionType.ELECTRONIC:
            continue
        power_links.append(
            _compile_power_link(edge_data, components_by_name, linked_power_targets)
        )

    # ------------------------------------------------------------------
    # Assembly
    # ------------------------------------------------------------------
    return HydraulicGraph(
        nodes=all_nodes,
        edges=all_edges,
        inventory_nodes=all_inventory,
        heat_links=heat_links,
        power_links=power_links,
    )
