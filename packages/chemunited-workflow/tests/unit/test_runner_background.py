"""RunnerService: background nodes keep running across processes and stop with the run."""

from __future__ import annotations

import json
import threading

import networkx as nx
import pytest
from pydantic import BaseModel

from chemunited_workflow import (
    NodeExecutionContext,
    Process,
    WorkflowEdgeSpec,
    WorkflowNodeSpec,
)
from chemunited_workflow.api.run_store import RunState, RunStore
from chemunited_workflow.api.services.runner import RunnerService


class Cfg(BaseModel):
    pass


class _Shared:
    """Cross-process observations for one test run (reset by the fixture)."""

    store: RunStore | None = None
    cancel_in_second = False
    bg_started = threading.Event()
    bg_stopped = threading.Event()
    bg_alive_during_second: bool | None = None


def _node(graph: nx.DiGraph, node_id: str, method: str, block_tag: str) -> None:
    graph.add_node(
        node_id,
        **WorkflowNodeSpec(node_id=node_id, method=method).model_dump(
            exclude_none=True
        ),
        block_tag=block_tag,
    )


def _edge(graph: nx.DiGraph, source: str, target: str) -> None:
    graph.add_edge(
        source,
        target,
        **WorkflowEdgeSpec(condition=True).model_dump(exclude_none=True),
    )


class FirstProcess(Process[Cfg]):
    """start → monitor (background), start → end."""

    def build_workflow(self) -> nx.DiGraph:
        graph = nx.DiGraph()
        _node(graph, "start", "start", "start")
        _node(graph, "end", "finish", "end")
        _node(graph, "monitor", "monitor", "background")
        _edge(graph, "start", "monitor")
        _edge(graph, "start", "end")
        return graph

    def start(self, ctx: NodeExecutionContext) -> bool:
        return True

    def monitor(self, ctx: NodeExecutionContext) -> bool:
        _Shared.bg_started.set()
        try:
            while not ctx.stop_requested:
                self.platform._wait(0.05)
        finally:
            _Shared.bg_stopped.set()
        return True

    def finish(self, ctx: NodeExecutionContext) -> bool:
        return True


class SecondProcess(Process[Cfg]):
    def build_workflow(self) -> nx.DiGraph:
        graph = nx.DiGraph()
        _node(graph, "start", "start", "start")
        _node(graph, "end", "finish", "end")
        _edge(graph, "start", "end")
        return graph

    def start(self, ctx: NodeExecutionContext) -> bool:
        assert _Shared.bg_started.wait(2)
        _Shared.bg_alive_during_second = not _Shared.bg_stopped.is_set()
        if _Shared.cancel_in_second and _Shared.store is not None:
            _Shared.store.cancel()
        return True

    def finish(self, ctx: NodeExecutionContext) -> bool:
        return True


@pytest.fixture
def runner(tmp_path):
    (tmp_path / "connectivity").mkdir()
    (tmp_path / "connectivity" / "associations.json").write_text(
        json.dumps({"associations": []}), encoding="utf-8"
    )
    store = RunStore()
    _Shared.store = store
    _Shared.cancel_in_second = False
    _Shared.bg_started = threading.Event()
    _Shared.bg_stopped = threading.Event()
    _Shared.bg_alive_during_second = None
    svc = RunnerService(
        project_dir=tmp_path,
        processes={"first": FirstProcess, "second": SecondProcess},
        configs={"first": Cfg, "second": Cfg},
        run_store=store,
    )
    return svc, store


def _execute(svc: RunnerService, run_id: str) -> None:
    svc._execute(
        run_id,
        "proto.json",
        [("first", 0), ("second", 0)],
        {"first_0": {}, "second_0": {}},
        dry_run=True,
        timeout_commands="1 s",
        error_resilient=False,
        record_monitoring=False,
    )


def test_background_node_runs_across_processes_and_stops_when_run_finishes(runner):
    svc, store = runner
    run_id = store.try_start("proto.json")
    assert run_id is not None

    _execute(svc, run_id)

    assert _Shared.bg_alive_during_second is True
    assert _Shared.bg_stopped.is_set()
    record = store.get()
    assert record is not None and record.state == RunState.FINISHED


def test_background_node_stops_when_run_is_cancelled(runner):
    svc, store = runner
    _Shared.cancel_in_second = True
    run_id = store.try_start("proto.json")
    assert run_id is not None

    _execute(svc, run_id)

    assert _Shared.bg_stopped.is_set()
    record = store.get()
    assert record is not None and record.state == RunState.CANCELLED
