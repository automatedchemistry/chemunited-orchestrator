"""Shared models used by the workflow compiler and executor."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import time
from typing import TYPE_CHECKING, Any, Callable, Self

import networkx as nx
from pydantic import BaseModel, ConfigDict, model_validator

from .enums import NodeState, WorkflowEventType

if TYPE_CHECKING:
    from .process import Process


class NodeConfig(BaseModel):
    """Base immutable node configuration."""

    model_config = ConfigDict(frozen=True)

    node_id: str


class WorkflowNodeSpec(BaseModel):
    """Author-time specification for a workflow node."""

    node_id: str
    method: str
    label: str = ""
    description: str = ""
    position: tuple[float, float] | None = None

    @model_validator(mode="after")
    def ensure_not_empty_label(self) -> Self:
        if not self.label:
            self.label = self.node_id
        return self


class WorkflowEdgeSpec(BaseModel):
    """Author-time specification for a normal conditional edge."""

    condition: bool
    label: str | None = None


class LoopBackSpec(BaseModel):
    """Specification for a loopback edge extracted from the authored graph."""

    source: str
    target: str
    trigger_on: bool
    max_iterations: int | None = None


@dataclass(slots=True)
class NodeRuntime:
    """Mutable node-local runtime state."""

    status_message: str = ""
    status_percentage: int = 0
    result: bool | None = None
    error: Exception | None = None
    started_at: float | None = None
    finished_at: float | None = None
    local_data: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class NodeExecutionContext:
    """Runtime context passed to user-defined node methods."""

    node_id: str
    iteration: int
    process: Process[Any]
    config: BaseModel
    node_config: NodeConfig | None
    runtime: NodeRuntime
    _progress_callback: Callable[[int, str | None, float | None], None] | None = field(
        default=None, repr=False
    )
    _input_callback: Callable[[str, float], str] | None = field(
        default=None, repr=False
    )

    def report_progress(
        self,
        percentage: int,
        message: str | None = None,
        wait_seconds: float | None = None,
    ) -> None:
        """Report live progress (0-100), an optional status message, and an
        optional wait duration (seconds) for this node.

        ``wait_seconds`` is a fire-once live signal for dashboards to render
        a countdown (e.g. before a fixed ``platform._wait(...)`` delay) — it
        is not persisted as run history and is cleared by the next progress
        report that omits it.
        """
        if self._progress_callback is not None:
            self._progress_callback(percentage, message, wait_seconds)

    def request_operator_input(self, message: str, timeout_seconds: float) -> str:
        """Show ``message`` on the dashboard and block until an operator replies.

        Raises ``OperatorInputTimeoutError`` if no reply arrives within
        ``timeout_seconds``, or ``RunCancelledError`` if the run is cancelled
        while waiting. Blocks only this node's worker thread — other nodes
        keep running.
        """
        if self._input_callback is None:
            raise RuntimeError(
                "request_operator_input() requires a run driven by the dashboard/API "
                "(no input callback is wired for this execution context)."
            )
        return self._input_callback(message, timeout_seconds)


@dataclass(slots=True)
class WorkflowExecutorState:
    """Mutable executor state keyed by ``(node_id, iteration)``."""

    node_state: dict[tuple[str, int], NodeState] = field(default_factory=dict)
    node_result: dict[tuple[str, int], bool | None] = field(default_factory=dict)
    node_runtime: dict[tuple[str, int], NodeRuntime] = field(default_factory=dict)
    active_predecessors: dict[tuple[str, int], set[tuple[str, int]]] = field(
        default_factory=dict
    )
    completed_predecessors: dict[tuple[str, int], set[tuple[str, int]]] = field(
        default_factory=dict
    )
    scheduled: dict[tuple[str, int], bool] = field(default_factory=dict)
    errors: dict[tuple[str, int], Exception] = field(default_factory=dict)


@dataclass(slots=True)
class WorkflowResult:
    """Final workflow execution result."""

    node_state: dict[tuple[str, int], NodeState]
    node_result: dict[tuple[str, int], bool | None]
    node_runtime: dict[tuple[str, int], NodeRuntime]
    errors: dict[tuple[str, int], Exception]
    process: str | None = None

    def model_dump(self) -> dict:
        return {
            "process": self.process,
            "node_state": {
                f"{k[0]}:{k[1]}": str(v) for k, v in self.node_state.items()
            },
            "node_result": {f"{k[0]}:{k[1]}": v for k, v in self.node_result.items()},
            "node_runtime": {
                f"{k[0]}:{k[1]}": {
                    "status_message": v.status_message,
                    "status_percentage": v.status_percentage,
                    "result": v.result,
                    "error": str(v.error) if v.error else None,
                    "started_at": v.started_at,
                    "finished_at": v.finished_at,
                    "local_data": v.local_data,
                }
                for k, v in self.node_runtime.items()
            },
            "errors": {f"{k[0]}:{k[1]}": str(v) for k, v in self.errors.items()},
        }


@dataclass(slots=True)
class WorkflowExecutionEvent:
    """Observable execution event emitted by the executor."""

    event_type: WorkflowEventType
    message: str
    node_key: tuple[str, int] | None = None
    process: str | None = None
    state: NodeState | None = None
    result: bool | None = None
    method: str | None = None
    source: str | None = None
    target: str | None = None
    active_predecessor_count: int | None = None
    completed_predecessor_count: int | None = None
    percentage: int | None = None
    wait_seconds: float | None = None
    input_value: str | None = None
    timestamp: float = field(default_factory=time)

    def model_dump(self) -> dict:
        return {
            "event_type": str(self.event_type),
            "message": self.message,
            "process": self.process,
            "node_key": list(self.node_key) if self.node_key else None,
            "state": str(self.state) if self.state else None,
            "result": self.result,
            "method": self.method,
            "source": self.source,
            "target": self.target,
            "active_predecessor_count": self.active_predecessor_count,
            "completed_predecessor_count": self.completed_predecessor_count,
            "percentage": self.percentage,
            "wait_seconds": self.wait_seconds,
            "input_value": self.input_value,
            "timestamp": self.timestamp,
        }

    def model_dump_json(self) -> str:
        import json as _json

        return _json.dumps(self.model_dump())


@dataclass(slots=True)
class CompiledWorkflow:
    """Compiled workflow artifacts."""

    user_graph: nx.DiGraph
    exec_graph: nx.DiGraph
    loopbacks: list[LoopBackSpec]
