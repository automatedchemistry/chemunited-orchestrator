"""Shared models used by the workflow compiler and executor."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import time
from typing import TYPE_CHECKING, Any

import networkx as nx
from pydantic import BaseModel, ConfigDict

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
    label: str | None = None
    description: str | None = None
    position: tuple[float, float] | None = None


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


@dataclass(slots=True)
class WorkflowExecutorState:
    """Mutable executor state keyed by ``(node_id, iteration)``."""

    node_state: dict[tuple[str, int], NodeState] = field(default_factory=dict)
    node_result: dict[tuple[str, int], bool | None] = field(default_factory=dict)
    node_runtime: dict[tuple[str, int], NodeRuntime] = field(default_factory=dict)
    active_predecessors: dict[tuple[str, int], set[tuple[str, int]]] = field(default_factory=dict)
    completed_predecessors: dict[tuple[str, int], set[tuple[str, int]]] = field(default_factory=dict)
    scheduled: dict[tuple[str, int], bool] = field(default_factory=dict)
    errors: dict[tuple[str, int], Exception] = field(default_factory=dict)


@dataclass(slots=True)
class WorkflowResult:
    """Final workflow execution result."""

    node_state: dict[tuple[str, int], NodeState]
    node_result: dict[tuple[str, int], bool | None]
    node_runtime: dict[tuple[str, int], NodeRuntime]
    errors: dict[tuple[str, int], Exception]


@dataclass(slots=True)
class WorkflowExecutionEvent:
    """Observable execution event emitted by the executor."""

    event_type: WorkflowEventType
    message: str
    node_key: tuple[str, int] | None = None
    state: NodeState | None = None
    result: bool | None = None
    method: str | None = None
    source: str | None = None
    target: str | None = None
    active_predecessor_count: int | None = None
    completed_predecessor_count: int | None = None
    timestamp: float = field(default_factory=time)


@dataclass(slots=True)
class CompiledWorkflow:
    """Compiled workflow artifacts."""

    user_graph: nx.DiGraph
    exec_graph: nx.DiGraph
    loopbacks: list[LoopBackSpec]
