"""Unit tests for cooperative workflow executor cancellation."""

from __future__ import annotations

import threading

import networkx as nx
from pydantic import BaseModel

from chemunited_workflow import (
    NodeExecutionContext,
    Process,
    WorkflowEdgeSpec,
    WorkflowExecutor,
    WorkflowNodeSpec,
    compile_workflow,
)
from chemunited_workflow.enums import NodeState


class CancelConfig(BaseModel):
    pass


class CancellingProcess(Process[CancelConfig]):
    def __init__(self, *args, cancel_event: threading.Event, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._cancel_event = cancel_event

    def build_workflow(self):
        graph = nx.DiGraph()
        graph.add_node(
            "start",
            **WorkflowNodeSpec(
                node_id="start",
                method="start",
                label="Start",
            ).model_dump(exclude_none=True),
        )
        graph.add_node(
            "finish",
            **WorkflowNodeSpec(
                node_id="finish",
                method="finish",
                label="Finish",
            ).model_dump(exclude_none=True),
        )
        graph.add_edge(
            "start",
            "finish",
            **WorkflowEdgeSpec(condition=True).model_dump(exclude_none=True),
        )
        return graph

    def start(self, ctx: NodeExecutionContext) -> bool:
        self._cancel_event.set()
        return True

    def finish(self, ctx: NodeExecutionContext) -> bool:
        return True


def test_executor_stops_scheduling_after_cancellation():
    cancel_event = threading.Event()
    process = CancellingProcess(
        config=CancelConfig(),
        cancel_event=cancel_event,
    )
    executor = WorkflowExecutor(
        compile_workflow(process.build_workflow()),
        cancellation_check=cancel_event.is_set,
    )

    result = executor.execute(process, start_node="start")

    assert result.node_state[("start", 0)] == NodeState.FAILED
    assert result.node_state[("finish", 0)] != NodeState.COMPLETED
