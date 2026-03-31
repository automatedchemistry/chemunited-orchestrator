"""Shared enums for workflow execution."""

from enum import StrEnum


class NodeState(StrEnum):
    """Lifecycle state for a node execution instance."""

    NOT_VISITED = "NOT_VISITED"
    WAITING = "WAITING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    INACTIVE = "INACTIVE"
    FAILED = "FAILED"


class WorkflowEventType(StrEnum):
    """Execution event types emitted by the workflow executor."""

    EXECUTION_STARTED = "EXECUTION_STARTED"
    ITERATION_STARTED = "ITERATION_STARTED"
    NODE_WAITING = "NODE_WAITING"
    NODE_RUNNING = "NODE_RUNNING"
    NODE_COMPLETED = "NODE_COMPLETED"
    NODE_INACTIVE = "NODE_INACTIVE"
    NODE_FAILED = "NODE_FAILED"
    LOOPBACK_TRIGGERED = "LOOPBACK_TRIGGERED"
    EXECUTION_FINISHED = "EXECUTION_FINISHED"
