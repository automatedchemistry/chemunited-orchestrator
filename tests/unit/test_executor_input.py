"""Unit tests for human-in-the-loop input via ctx.request_operator_input()."""

from __future__ import annotations

import networkx as nx
from pydantic import BaseModel
import pytest

from chemunited_workflow import (
    NodeExecutionContext,
    NodeState,
    OperatorInputTimeoutError,
    Process,
    RunCancelledError,
    WorkflowEdgeSpec,
    WorkflowExecutor,
    WorkflowNodeSpec,
    compile_workflow,
)
from chemunited_workflow.enums import WorkflowEventType


class InputConfig(BaseModel):
    pass


class InputProcess(Process[InputConfig]):
    def build_workflow(self):
        graph = nx.DiGraph()
        graph.add_node(
            "start",
            **WorkflowNodeSpec(
                node_id="start", method="start", label="Start"
            ).model_dump(exclude_none=True),
        )
        graph.add_node(
            "finish",
            **WorkflowNodeSpec(
                node_id="finish", method="finish", label="Finish"
            ).model_dump(exclude_none=True),
        )
        graph.add_edge(
            "start",
            "finish",
            **WorkflowEdgeSpec(condition=True).model_dump(exclude_none=True),
        )
        return graph

    def start(self, ctx: NodeExecutionContext) -> bool:
        self.reply = ctx.request_operator_input(
            "Confirm reagent loaded", timeout_seconds=5.0
        )
        return True

    def finish(self, ctx: NodeExecutionContext) -> bool:
        return True


def test_request_operator_input_returns_delivered_value_and_emits_events():
    process = InputProcess(config=InputConfig())
    events = []
    executor = WorkflowExecutor(
        compile_workflow(process.build_workflow()),
        event_listeners=[events.append],
        request_input=lambda node_id, message, timeout_seconds: "yes",
    )

    result = executor.execute(process, start_node="start")

    assert process.reply == "yes"
    assert not result.errors

    start_events = [e for e in events if e.node_key == ("start", 0)]
    requested = next(
        e
        for e in start_events
        if e.event_type == WorkflowEventType.NODE_INPUT_REQUESTED
    )
    received = next(
        e for e in start_events if e.event_type == WorkflowEventType.NODE_INPUT_RECEIVED
    )
    assert requested.message == "Confirm reagent loaded"
    assert received.input_value == "yes"
    assert start_events.index(requested) < start_events.index(received)


def test_request_operator_input_passes_node_id_and_timeout_to_callable():
    process = InputProcess(config=InputConfig())
    captured = {}

    def request_input(node_id: str, message: str, timeout_seconds: float) -> str:
        captured["node_id"] = node_id
        captured["message"] = message
        captured["timeout_seconds"] = timeout_seconds
        return "ok"

    executor = WorkflowExecutor(
        compile_workflow(process.build_workflow()),
        request_input=request_input,
    )
    executor.execute(process, start_node="start")

    assert captured == {
        "node_id": "start",
        "message": "Confirm reagent loaded",
        "timeout_seconds": 5.0,
    }


def test_request_operator_input_timeout_fails_the_node():
    process = InputProcess(config=InputConfig())

    def request_input(node_id: str, message: str, timeout_seconds: float) -> str:
        raise OperatorInputTimeoutError("no reply")

    executor = WorkflowExecutor(
        compile_workflow(process.build_workflow()),
        request_input=request_input,
    )
    result = executor.execute(process, start_node="start")

    assert result.node_state[("start", 0)] == NodeState.FAILED
    assert isinstance(result.errors[("start", 0)], OperatorInputTimeoutError)


def test_request_operator_input_cancellation_stops_the_run():
    process = InputProcess(config=InputConfig())

    def request_input(node_id: str, message: str, timeout_seconds: float) -> str:
        raise RunCancelledError("run was cancelled")

    executor = WorkflowExecutor(
        compile_workflow(process.build_workflow()),
        request_input=request_input,
    )
    result = executor.execute(process, start_node="start")

    assert result.node_state[("start", 0)] == NodeState.FAILED
    assert ("finish", 0) not in result.node_state or result.node_state[
        ("finish", 0)
    ] != NodeState.COMPLETED


def test_request_operator_input_without_callable_raises_runtime_error():
    process = InputProcess(config=InputConfig())
    executor = WorkflowExecutor(compile_workflow(process.build_workflow()))

    result = executor.execute(process, start_node="start")

    assert result.node_state[("start", 0)] == NodeState.FAILED
    assert isinstance(result.errors[("start", 0)], RuntimeError)


def test_report_progress_input_user_kwarg_does_not_exist():
    """Guards the API decision: input_user is a dedicated method, not a
    report_progress() kwarg — request_operator_input() is the public entry
    point instead."""
    ctx = NodeExecutionContext(
        node_id="n",
        iteration=0,
        process=None,
        config=None,
        node_config=None,
        runtime=None,
    )
    with pytest.raises(TypeError):
        ctx.report_progress(50, input_user=True)  # type: ignore[call-arg]
