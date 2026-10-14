"""Unit tests for background workflow nodes (``block_tag="background"``)."""

from __future__ import annotations

import threading
import time

import networkx as nx
import pytest
from pydantic import BaseModel

from chemunited_workflow import (
    NodeExecutionContext,
    Process,
    WorkflowEdgeSpec,
    WorkflowExecutor,
    WorkflowNodeSpec,
    compile_workflow,
)
from chemunited_workflow.background import BackgroundTasks
from chemunited_workflow.enums import NodeState, WorkflowEventType


class BgConfig(BaseModel):
    pass


def _add_node(graph: nx.DiGraph, node_id: str, method: str, block_tag: str) -> None:
    graph.add_node(
        node_id,
        **WorkflowNodeSpec(node_id=node_id, method=method).model_dump(
            exclude_none=True
        ),
        block_tag=block_tag,
    )


def _add_edge(graph: nx.DiGraph, source: str, target: str) -> None:
    graph.add_edge(
        source,
        target,
        **WorkflowEdgeSpec(condition=True).model_dump(exclude_none=True),
    )


def _background_graph() -> nx.DiGraph:
    """start → bg (background leaf), start → work → end."""
    graph = nx.DiGraph()
    _add_node(graph, "start", "start", "start")
    _add_node(graph, "end", "finish", "end")
    _add_node(graph, "work", "work", "script")
    _add_node(graph, "bg", "bg", "background")
    _add_edge(graph, "start", "bg")
    _add_edge(graph, "start", "work")
    _add_edge(graph, "work", "end")
    return graph


class BackgroundProcess(Process[BgConfig]):
    def __init__(self, *args, fail: bool = False, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fail = fail
        self.bg_started = threading.Event()

    def build_workflow(self) -> nx.DiGraph:
        return _background_graph()

    def start(self, ctx: NodeExecutionContext) -> bool:
        return True

    def bg(self, ctx: NodeExecutionContext) -> bool:
        self.bg_started.set()
        if self.fail:
            raise RuntimeError("analytics offline")
        while not ctx.stop_requested:
            time.sleep(0.01)
        return True

    def work(self, ctx: NodeExecutionContext) -> bool:
        assert self.bg_started.wait(2)
        return True

    def finish(self, ctx: NodeExecutionContext) -> bool:
        return True


def _bg_events(events, event_type: WorkflowEventType):
    return [
        e
        for e in events
        if e.event_type == event_type
        and e.node_key is not None
        and e.node_key[0] == "bg"
    ]


# ── compile ──────────────────────────────────────────────────────────────────


def test_compile_collects_background_nodes():
    compiled = compile_workflow(_background_graph())
    assert compiled.background_nodes == frozenset({"bg"})


def test_compile_without_background_tag_has_no_background_nodes():
    graph = _background_graph()
    graph.nodes["bg"]["block_tag"] = "script"
    assert compile_workflow(graph).background_nodes == frozenset()


def test_compile_rejects_background_node_with_outgoing_edge():
    graph = _background_graph()
    _add_edge(graph, "bg", "end")
    with pytest.raises(ValueError, match="must not have outgoing connections"):
        compile_workflow(graph)


def test_compile_rejects_background_node_as_loopback_source():
    graph = _background_graph()
    graph.add_edge("bg", "start", loopback=True, trigger_on=True)
    with pytest.raises(ValueError, match="must not have outgoing connections"):
        compile_workflow(graph)


# ── execute with a run-level host ─────────────────────────────────────────────


def test_execute_does_not_wait_for_background_node():
    stop = threading.Event()
    host = BackgroundTasks()
    events: list = []
    process = BackgroundProcess(config=BgConfig())
    executor = WorkflowExecutor(
        compile_workflow(process.build_workflow()),
        event_listeners=[events.append],
        cancellation_check=stop.is_set,
        background=host,
    )

    result = executor.execute(process, start_node="start")

    assert result.node_state[("end", 0)] == NodeState.COMPLETED
    assert result.node_state[("bg", 0)] == NodeState.RUNNING
    assert host.join(0) != []  # still running after the process finished

    stop.set()
    assert host.join(5) == []
    completed = _bg_events(events, WorkflowEventType.NODE_COMPLETED)
    assert completed[-1].message == "Background module stopped with the run."


def test_background_node_failure_is_logged_not_recorded():
    stop = threading.Event()
    host = BackgroundTasks()
    events: list = []
    process = BackgroundProcess(config=BgConfig(), fail=True)
    executor = WorkflowExecutor(
        compile_workflow(process.build_workflow()),
        event_listeners=[events.append],
        cancellation_check=stop.is_set,
        background=host,
    )

    result = executor.execute(process, start_node="start")
    assert host.join(5) == []

    assert result.errors == {}
    assert result.node_state[("end", 0)] == NodeState.COMPLETED
    failed = _bg_events(events, WorkflowEventType.NODE_FAILED)
    assert len(failed) == 1
    assert "analytics offline" in failed[0].message


def test_stop_requested_is_true_after_cancellation():
    stop = threading.Event()
    seen: list[bool] = []

    class Probe(BackgroundProcess):
        def work(self, ctx: NodeExecutionContext) -> bool:
            seen.append(ctx.stop_requested)
            stop.set()
            seen.append(ctx.stop_requested)
            return True

    process = Probe(config=BgConfig())
    host = BackgroundTasks()
    WorkflowExecutor(
        compile_workflow(process.build_workflow()),
        cancellation_check=stop.is_set,
        background=host,
    ).execute(process, start_node="start")
    host.join(5)

    assert seen == [False, True]


# ── standalone execute (no host) ──────────────────────────────────────────────


def test_standalone_execute_stops_its_own_background_nodes():
    process = BackgroundProcess(config=BgConfig())
    executor = WorkflowExecutor(compile_workflow(process.build_workflow()))

    result = executor.execute(process, start_node="start")

    # The executor hosted the node itself and stopped it once the workflow
    # finished — so it has already completed, with no run-level token involved.
    assert result.node_state[("bg", 0)] == NodeState.COMPLETED
    assert result.node_state[("end", 0)] == NodeState.COMPLETED
    assert result.errors == {}
