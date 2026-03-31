"""Example workflow showing conditional fan-out, joins, and loopbacks."""

from __future__ import annotations

import sys
from pathlib import Path
from time import sleep

import networkx as nx
from pydantic import BaseModel, ConfigDict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chemunited_workflow import (
    NodeConfig,
    NodeExecutionContext,
    Process,
    TerminalWorkflowObserver,
    WorkflowEdgeSpec,
    WorkflowExecutor,
    WorkflowNodeSpec,
    compile_workflow,
    configure_terminal_logging,
)


class UserProcessConfig(BaseModel):
    """Immutable process configuration shared across all nodes."""

    model_config = ConfigDict(frozen=True)

    primary_route: bool
    loopback_success_iteration: int
    default_delay_s: float = 0.15


class UserNodeConfig(NodeConfig):
    """Per-node immutable settings."""

    model_config = ConfigDict(frozen=True)

    delay_s: float
    note: str


class CustomProcess(Process[UserProcessConfig]):
    """User-defined workflow process."""

    def build_workflow(self) -> nx.DiGraph:
        graph = nx.DiGraph()

        def add_node(node_id: str, method: str, label: str, description: str, delay_s: float) -> None:
            graph.add_node(
                node_id,
                **WorkflowNodeSpec(
                    node_id=node_id,
                    method=method,
                    label=label,
                    description=description,
                ).model_dump(exclude_none=True),
                node_config=UserNodeConfig(
                    node_id=node_id,
                    delay_s=delay_s,
                    note=description,
                ),
            )

        add_node("IN", "enter", "Entry", "Start the workflow", 0.5)
        add_node("0", "check_pressure", "Initial check", "Choose the main route", 1)
        add_node("1", "handle_low_pressure", "Fallback branch", "Runs only when the initial check is false", 2)
        add_node("2", "join_primary_paths", "Join", "Joins only the active predecessors", 1)
        add_node("3", "initialize_reactor", "Primary branch", "Primary setup branch", 3)
        add_node("4", "prepare_analysis", "Analysis split", "Starts the parallel analysis branch", 1)
        add_node("5", "send_report", "Report", "Independent reporting branch", 2)
        add_node("6", "collect_signal", "Signal", "Collect analysis output", 2)
        add_node("7", "validate_signal", "Validation", "May request a loopback retry", 1)
        add_node("OUT", "finish", "Finish", "Finalize the workflow", 5)

        graph.add_edge("IN", "0", **WorkflowEdgeSpec(condition=True, label="start").model_dump(exclude_none=True))
        graph.add_edge("0", "1", **WorkflowEdgeSpec(condition=False, label="low pressure").model_dump(exclude_none=True))
        graph.add_edge("0", "3", **WorkflowEdgeSpec(condition=True, label="primary").model_dump(exclude_none=True))
        graph.add_edge("0", "4", **WorkflowEdgeSpec(condition=True, label="fan-out").model_dump(exclude_none=True))
        graph.add_edge("1", "2", **WorkflowEdgeSpec(condition=True, label="recover").model_dump(exclude_none=True))
        graph.add_edge("3", "2", **WorkflowEdgeSpec(condition=True, label="join").model_dump(exclude_none=True))
        graph.add_edge("4", "5", **WorkflowEdgeSpec(condition=True, label="report").model_dump(exclude_none=True))
        graph.add_edge("4", "6", **WorkflowEdgeSpec(condition=True, label="measure").model_dump(exclude_none=True))
        graph.add_edge("6", "7", **WorkflowEdgeSpec(condition=True, label="validate").model_dump(exclude_none=True))
        graph.add_edge("2", "OUT", **WorkflowEdgeSpec(condition=True, label="done").model_dump(exclude_none=True))
        graph.add_edge("5", "OUT", **WorkflowEdgeSpec(condition=True, label="done").model_dump(exclude_none=True))
        graph.add_edge("7", "OUT", **WorkflowEdgeSpec(condition=True, label="done").model_dump(exclude_none=True))
        graph.add_edge("7", "4", loopback=True, trigger_on=False, max_iterations=2, label="retry analysis")

        return graph

    def _pause(self, ctx: NodeExecutionContext) -> None:
        delay_s = self.config.default_delay_s
        if isinstance(ctx.node_config, UserNodeConfig):
            delay_s = ctx.node_config.delay_s
            ctx.runtime.local_data["note"] = ctx.node_config.note
        sleep(delay_s)

    def enter(self, ctx: NodeExecutionContext) -> bool:
        self._pause(ctx)
        ctx.runtime.status_message = "Entered the workflow."
        return True

    def check_pressure(self, ctx: NodeExecutionContext) -> bool:
        self._pause(ctx)
        ctx.runtime.local_data["primary_route"] = self.config.primary_route
        ctx.runtime.status_message = f"Primary route selected: {self.config.primary_route}"
        return self.config.primary_route

    def handle_low_pressure(self, ctx: NodeExecutionContext) -> bool:
        self._pause(ctx)
        ctx.runtime.status_message = "Low-pressure fallback completed."
        return True

    def initialize_reactor(self, ctx: NodeExecutionContext) -> bool:
        self._pause(ctx)
        ctx.runtime.status_message = "Primary reactor branch completed."
        return True

    def join_primary_paths(self, ctx: NodeExecutionContext) -> bool:
        self._pause(ctx)
        ctx.runtime.status_message = "Join node ran after only the active predecessors completed."
        return True

    def prepare_analysis(self, ctx: NodeExecutionContext) -> bool:
        self._pause(ctx)
        ctx.runtime.status_message = f"Preparing analysis for iteration {ctx.iteration}."
        return True

    def send_report(self, ctx: NodeExecutionContext) -> bool:
        self._pause(ctx)
        ctx.runtime.status_message = f"Report sent for iteration {ctx.iteration}."
        return True

    def collect_signal(self, ctx: NodeExecutionContext) -> bool:
        self._pause(ctx)
        ctx.runtime.status_message = f"Signal collected for iteration {ctx.iteration}."
        return True

    def validate_signal(self, ctx: NodeExecutionContext) -> bool:
        self._pause(ctx)
        passed = ctx.iteration >= self.config.loopback_success_iteration
        ctx.runtime.status_message = f"Validation passed={passed} for iteration {ctx.iteration}."
        return passed

    def finish(self, ctx: NodeExecutionContext) -> bool:
        self._pause(ctx)
        ctx.runtime.status_message = f"Workflow finished in iteration {ctx.iteration}."
        return True

def main() -> None:
    """Build, compile, and execute the example workflow."""

    configure_terminal_logging()
    config = UserProcessConfig(
        primary_route=True,
        loopback_success_iteration=1,
    )
    process = CustomProcess(config)

    authored_graph = process.build_workflow()
    compiled = compile_workflow(authored_graph)
    terminal = TerminalWorkflowObserver(compiled, refresh_per_second=6)
    executor = WorkflowExecutor(compiled, max_workers=4, event_listeners=[terminal.handle_event])
    result = executor.execute(process, start_node="IN")
    terminal.print_execution_report(result, authored_graph=authored_graph)


if __name__ == "__main__":
    main()
