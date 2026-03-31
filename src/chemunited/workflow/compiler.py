"""Compilation helpers for workflow graphs."""

from __future__ import annotations

from typing import Any

import networkx as nx

from .models import CompiledWorkflow, LoopBackSpec, NodeConfig, WorkflowEdgeSpec, WorkflowNodeSpec


def compile_workflow(user_graph: nx.DiGraph) -> CompiledWorkflow:
    """Compile an authored workflow graph into an executable DAG plus loopbacks."""

    user_graph_copy = user_graph.copy(as_view=False)

    exec_graph = nx.DiGraph()
    exec_graph.graph.update(dict(user_graph.graph))

    for node_id, node_data in user_graph.nodes(data=True):
        attrs = dict(node_data)
        _validate_node(node_id, attrs)
        exec_graph.add_node(node_id, **attrs)

    loopbacks: list[LoopBackSpec] = []
    loopback_targets: dict[tuple[str, bool], str] = {}

    for source, target, edge_data in user_graph.edges(data=True):
        attrs = dict(edge_data)
        if attrs.get("loopback") is True:
            loopback = _build_loopback(source, target, attrs)
            key = (loopback.source, loopback.trigger_on)
            if key in loopback_targets:
                existing_target = loopback_targets[key]
                raise ValueError(
                    "Only one loopback target is supported per source/trigger pair. "
                    f"Found both {existing_target!r} and {loopback.target!r} for "
                    f"source={loopback.source!r}, trigger_on={loopback.trigger_on!r}."
                )
            loopback_targets[key] = loopback.target
            loopbacks.append(loopback)
            continue

        _validate_normal_edge(source, target, attrs)
        exec_graph.add_edge(source, target, **attrs)

    if not nx.is_directed_acyclic_graph(exec_graph):
        cycle = nx.find_cycle(exec_graph, orientation="original")
        cycle_text = " -> ".join(edge[0] for edge in cycle + [cycle[0]])
        raise ValueError(
            "The compiled executable workflow must be a DAG. "
            f"Cycle detected in executable edges: {cycle_text}."
        )

    return CompiledWorkflow(user_graph=user_graph_copy, exec_graph=exec_graph, loopbacks=loopbacks)


def _validate_node(node_id: str, attrs: dict[str, Any]) -> None:
    WorkflowNodeSpec(
        node_id=node_id,
        method=attrs.get("method"),
        label=attrs.get("label"),
        description=attrs.get("description"),
        position=attrs.get("position"),
    )

    node_config = attrs.get("node_config")
    if node_config is None:
        return

    if not isinstance(node_config, NodeConfig):
        raise TypeError(
            f"Node {node_id!r} has invalid 'node_config'. Expected a NodeConfig instance, "
            f"got {type(node_config).__name__}."
        )

    if node_config.node_id != node_id:
        raise ValueError(
            f"Node {node_id!r} has node_config.node_id={node_config.node_id!r}. "
            "Those values must match."
        )


def _validate_normal_edge(source: str, target: str, attrs: dict[str, Any]) -> None:
    try:
        condition = attrs["condition"]
    except KeyError as exc:
        raise ValueError(
            f"Normal edge {source!r} -> {target!r} is missing the required 'condition' attribute."
        ) from exc

    if not isinstance(condition, bool):
        raise TypeError(
            f"Normal edge {source!r} -> {target!r} has invalid condition={condition!r}. "
            "Expected a bool."
        )

    WorkflowEdgeSpec(condition=condition, label=attrs.get("label"))


def _build_loopback(source: str, target: str, attrs: dict[str, Any]) -> LoopBackSpec:
    if "trigger_on" not in attrs:
        raise ValueError(
            f"Loopback edge {source!r} -> {target!r} is missing the required 'trigger_on' attribute."
        )

    trigger_on = attrs["trigger_on"]
    if not isinstance(trigger_on, bool):
        raise TypeError(
            f"Loopback edge {source!r} -> {target!r} has invalid trigger_on={trigger_on!r}. "
            "Expected a bool."
        )

    max_iterations = attrs.get("max_iterations")
    if max_iterations is not None:
        if not isinstance(max_iterations, int) or max_iterations < 0:
            raise TypeError(
                f"Loopback edge {source!r} -> {target!r} has invalid max_iterations={max_iterations!r}. "
                "Expected a non-negative int or None."
            )

    return LoopBackSpec(
        source=source,
        target=target,
        trigger_on=trigger_on,
        max_iterations=max_iterations,
    )
