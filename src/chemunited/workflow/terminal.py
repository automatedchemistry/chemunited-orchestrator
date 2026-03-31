"""Terminal-oriented helpers for workflow execution events and reports."""

from __future__ import annotations

import sys
from collections import deque
from threading import RLock
from typing import Any

import networkx as nx
from loguru import logger
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .enums import NodeState, WorkflowEventType
from .models import CompiledWorkflow, WorkflowExecutionEvent, WorkflowResult

NodeKey = tuple[str, int]

_STATE_STYLES: dict[NodeState, str] = {
    NodeState.NOT_VISITED: "dim",
    NodeState.WAITING: "yellow",
    NodeState.RUNNING: "cyan",
    NodeState.COMPLETED: "green",
    NodeState.INACTIVE: "bright_black",
    NodeState.FAILED: "bold red",
}


def configure_terminal_logging(
    *,
    level: str = "INFO",
    sink: Any | None = None,
    colorize: bool = True,
) -> None:
    """Configure loguru for terminal-oriented workflow output."""

    logger.remove()
    logger.add(
        sink or sys.stderr,
        level=level,
        colorize=colorize,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
    )


class TerminalWorkflowObserver:
    """Consume workflow execution events and render them in the terminal."""

    def __init__(
        self,
        compiled_workflow: CompiledWorkflow,
        *,
        console: Console | None = None,
        refresh_per_second: int = 8,
        max_events: int = 12,
        enable_loguru: bool = True,
        enable_live: bool = True,
    ) -> None:
        self._compiled = compiled_workflow
        self._console = console or Console()
        self._refresh_per_second = refresh_per_second
        self._enable_loguru = enable_loguru
        self._enable_live = enable_live
        self._live: Live | None = None
        self._lock = RLock()
        self._logger = logger.bind(component="workflow.terminal")
        self._recent_events: deque[str] = deque(maxlen=max_events)
        self._node_rows: dict[NodeKey, dict[str, Any]] = {}

    def handle_event(self, event: WorkflowExecutionEvent) -> None:
        """Consume a workflow execution event."""

        with self._lock:
            if (
                self._enable_live
                and self._live is None
                and event.event_type == WorkflowEventType.EXECUTION_STARTED
            ):
                self._live = Live(
                    self._render_live_layout(),
                    console=self._console,
                    refresh_per_second=self._refresh_per_second,
                    transient=False,
                )
                self._live.start()

            if event.node_key is not None:
                row = self._node_rows.setdefault(
                    event.node_key,
                    {
                        "state": NodeState.NOT_VISITED,
                        "result": None,
                        "message": "",
                        "method": None,
                        "active_predecessor_count": 0,
                        "completed_predecessor_count": 0,
                    },
                )
                if event.state is not None:
                    row["state"] = event.state
                if event.result is not None or event.event_type == WorkflowEventType.NODE_COMPLETED:
                    row["result"] = event.result
                if event.method is not None:
                    row["method"] = event.method
                if event.active_predecessor_count is not None:
                    row["active_predecessor_count"] = event.active_predecessor_count
                if event.completed_predecessor_count is not None:
                    row["completed_predecessor_count"] = event.completed_predecessor_count
                row["message"] = event.message

            formatted_message = self._format_event_message(event)
            self._recent_events.append(formatted_message)

            if self._enable_loguru:
                self._logger.info(formatted_message)

            if self._live is not None:
                self._live.update(self._render_live_layout())
                if event.event_type == WorkflowEventType.EXECUTION_FINISHED:
                    self._live.stop()
                    self._live = None

    def print_execution_report(
        self,
        result: WorkflowResult,
        *,
        authored_graph: nx.DiGraph | None = None,
        show_authored_graph: bool = True,
        show_exec_graph: bool = True,
    ) -> None:
        """Print a final terminal report after execution."""

        if show_authored_graph and authored_graph is not None:
            self._console.print(
                Panel.fit(self._format_graph_edges(authored_graph), title="Authored Graph Edges")
            )
        if show_exec_graph:
            self._console.print(
                Panel.fit(self._format_graph_edges(self._compiled.exec_graph), title="Executable DAG Edges")
            )

        self._console.print(self.build_loopbacks_table())
        self._console.print(self.build_result_summary_table(result))
        self._console.print(self.build_errors_table(result))

    def build_loopbacks_table(self) -> Table:
        """Build a table describing compiled loopbacks."""

        table = Table(title="Compiled Loopbacks", expand=True)
        table.add_column("Source")
        table.add_column("Target")
        table.add_column("Trigger")
        table.add_column("Max Iterations")

        if not self._compiled.loopbacks:
            table.add_row("-", "-", "-", "-")
            return table

        for loopback in self._compiled.loopbacks:
            table.add_row(
                loopback.source,
                loopback.target,
                str(loopback.trigger_on),
                str(loopback.max_iterations),
            )

        return table

    def build_result_summary_table(self, result: WorkflowResult) -> Table:
        """Build a final execution summary table."""

        table = Table(title="Execution Summary", expand=True)
        table.add_column("Iteration", justify="right")
        table.add_column("Node")
        table.add_column("State")
        table.add_column("Result")
        table.add_column("Message")

        for node_key in sorted(result.node_state, key=lambda item: (item[1], item[0])):
            state = result.node_state[node_key]
            runtime = result.node_runtime[node_key]
            result_value = result.node_result.get(node_key)
            table.add_row(
                str(node_key[1]),
                node_key[0],
                state.value,
                "-" if result_value is None else str(result_value),
                runtime.status_message,
            )

        return table

    def build_errors_table(self, result: WorkflowResult) -> Table:
        """Build a table summarizing execution errors."""

        table = Table(title="Execution Errors", expand=True)
        table.add_column("Iteration", justify="right")
        table.add_column("Node")
        table.add_column("Error")

        if result.errors:
            for node_key, error in result.errors.items():
                table.add_row(str(node_key[1]), node_key[0], str(error))
        else:
            table.add_row("-", "-", "No errors")

        return table

    def _render_live_layout(self) -> Group:
        return Group(
            Panel(self._build_summary_table(), title="Workflow Summary", border_style="blue"),
            Panel(self._build_nodes_table(), title="Node States", border_style="magenta"),
            Panel(self._build_event_log(), title="Recent Events", border_style="green"),
        )

    def _build_summary_table(self) -> Table:
        summary = Table.grid(expand=True)
        summary.add_column(justify="left")
        summary.add_column(justify="left")
        summary.add_column(justify="left")

        counts: dict[NodeState, int] = {state: 0 for state in NodeState}
        for row in self._node_rows.values():
            counts[row["state"]] += 1

        state_text = Text()
        for state in NodeState:
            if state_text.plain:
                state_text.append("  ")
            state_text.append(f"{state.value}: {counts[state]}", style=_STATE_STYLES[state])

        loopback_text = ", ".join(
            f"{spec.source}->{spec.target} on {spec.trigger_on}" for spec in self._compiled.loopbacks
        ) or "none"

        summary.add_row("Tracked nodes", str(len(self._node_rows)), f"Loopbacks: {loopback_text}")
        summary.add_row("State counts", state_text, "")
        return summary

    def _build_nodes_table(self) -> Table:
        table = Table(expand=True, show_lines=False)
        table.add_column("Iteration", justify="right", no_wrap=True)
        table.add_column("Node", no_wrap=True)
        table.add_column("State", no_wrap=True)
        table.add_column("Result", no_wrap=True)
        table.add_column("Active", justify="right", no_wrap=True)
        table.add_column("Active Done", justify="right", no_wrap=True)
        table.add_column("Method", no_wrap=True)
        table.add_column("Message", overflow="fold")

        for node_key in sorted(self._node_rows, key=lambda item: (item[1], item[0])):
            row = self._node_rows[node_key]
            method = row["method"]
            if method is None and node_key[0] in self._compiled.exec_graph:
                method = self._compiled.exec_graph.nodes[node_key[0]].get("method", "-")

            result = row["result"]
            table.add_row(
                str(node_key[1]),
                node_key[0],
                Text(row["state"].value, style=_STATE_STYLES[row["state"]]),
                "-" if result is None else str(result),
                str(row["active_predecessor_count"]),
                str(row["completed_predecessor_count"]),
                str(method or "-"),
                str(row["message"]),
            )

        if not self._node_rows:
            table.add_row("-", "-", "NOT_STARTED", "-", "-", "-", "-", "Waiting for execution start.")

        return table

    def _build_event_log(self) -> Text:
        if not self._recent_events:
            return Text("No execution events yet.", style="dim")

        log_text = Text()
        for index, message in enumerate(self._recent_events):
            if index:
                log_text.append("\n")
            log_text.append(message)
        return log_text

    def _format_event_message(self, event: WorkflowExecutionEvent) -> str:
        node_fragment = ""
        if event.node_key is not None:
            node_fragment = f"[{event.node_key[0]}@{event.node_key[1]}] "

        if event.event_type == WorkflowEventType.LOOPBACK_TRIGGERED:
            return (
                f"{event.event_type}: {node_fragment}{event.message} "
                f"({event.source} -> {event.target})"
            )

        return f"{event.event_type}: {node_fragment}{event.message}"

    @staticmethod
    def _format_graph_edges(graph: nx.DiGraph) -> str:
        return str(list(graph.edges(data=True)))


RichWorkflowMonitor = TerminalWorkflowObserver

