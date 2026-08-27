"""Unit tests for live node progress reporting via ctx.report_progress()."""

from __future__ import annotations

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
from chemunited_workflow.enums import WorkflowEventType


class ProgressConfig(BaseModel):
    pass


class ProgressProcess(Process[ProgressConfig]):
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
        ctx.report_progress(50, "halfway")
        ctx.report_progress(150, "over the top")  # out-of-range, should clamp to 100
        return True

    def finish(self, ctx: NodeExecutionContext) -> bool:
        return True


def test_report_progress_emits_node_progress_events_between_running_and_completed():
    process = ProgressProcess(config=ProgressConfig())
    events = []
    executor = WorkflowExecutor(
        compile_workflow(process.build_workflow()),
        event_listeners=[events.append],
    )

    executor.execute(process, start_node="start")

    start_events = [e for e in events if e.node_key == ("start", 0)]
    progress_events = [
        e for e in start_events if e.event_type == WorkflowEventType.NODE_PROGRESS
    ]

    assert [e.percentage for e in progress_events] == [50, 100]
    assert progress_events[0].message == "halfway"
    assert progress_events[1].message == "over the top"

    running_index = next(
        i
        for i, e in enumerate(start_events)
        if e.event_type == WorkflowEventType.NODE_RUNNING
    )
    completed_index = next(
        i
        for i, e in enumerate(start_events)
        if e.event_type == WorkflowEventType.NODE_COMPLETED
    )
    progress_indices = [
        i
        for i, e in enumerate(start_events)
        if e.event_type == WorkflowEventType.NODE_PROGRESS
    ]
    assert all(running_index < i < completed_index for i in progress_indices)
    assert start_events[completed_index].percentage == 100


def test_node_completion_always_reports_full_percentage():
    process = ProgressProcess(config=ProgressConfig())
    executor = WorkflowExecutor(compile_workflow(process.build_workflow()))

    result = executor.execute(process, start_node="start")

    # "finish" never calls report_progress, but completion still fills the bar.
    assert result.node_runtime[("finish", 0)].status_percentage == 100
    assert result.node_runtime[("start", 0)].status_percentage == 100


class WaitProcess(Process[ProgressConfig]):
    def build_workflow(self):
        graph = nx.DiGraph()
        graph.add_node(
            "start",
            **WorkflowNodeSpec(
                node_id="start", method="start", label="Start"
            ).model_dump(exclude_none=True),
        )
        return graph

    def start(self, ctx: NodeExecutionContext) -> bool:
        ctx.report_progress(50, "waiting", wait_seconds=30)
        ctx.report_progress(100, "done")
        return True


def test_report_progress_wait_seconds_is_carried_then_cleared():
    process = WaitProcess(config=ProgressConfig())
    events = []
    executor = WorkflowExecutor(
        compile_workflow(process.build_workflow()),
        event_listeners=[events.append],
    )

    executor.execute(process, start_node="start")

    progress_events = [
        e for e in events if e.event_type == WorkflowEventType.NODE_PROGRESS
    ]

    assert progress_events[0].wait_seconds == 30
    assert progress_events[1].wait_seconds is None
