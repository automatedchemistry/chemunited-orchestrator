"""Loguru-based workflow logger and terminal helpers."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from .enums import NodeState
from .models import WorkflowExecutionEvent


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


def create_run_log_path(project_dir: Path | str, snapshot_filename: str) -> Path:
    """Return the log file path for a given run.

    Example: snapshot ``test_2026-05-15T10-38-00.json`` in project dir
    ``examples/custom_project`` becomes
    ``examples/custom_project/log/test_2026-05-15T10-38-00_executed_2026-05-19T14-00-00.log``.
    """
    stem = Path(snapshot_filename).stem
    now = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    return Path(project_dir) / "log" / f"{stem}_executed_{now}.log"


_STATE_LEVEL = {
    NodeState.FAILED: "error",
    NodeState.WAITING: "debug",
    NodeState.COMPLETED: "success",
    NodeState.INACTIVE: "debug",
    NodeState.NOT_VISITED: "debug",
}


class WorkflowLogger:
    """Emit one loguru line per workflow execution event."""

    def __init__(self, process_name: str, process_index: int) -> None:
        self._prefix = f"PROCESS: {process_name}_{process_index}"

    def handle_event(self, event: WorkflowExecutionEvent) -> None:
        if event.node_key is not None:
            node_id, iteration = event.node_key
            state_label = (
                event.state.value if event.state is not None else event.event_type.value
            )
            tag = f"[{self._prefix}, NODE: {node_id}] {state_label}"
            level = (
                _STATE_LEVEL.get(event.state, "info")
                if event.state is not None
                else "info"
            )
        else:
            tag = f"[{self._prefix}] {event.event_type.value}"
            level = "info"

        getattr(logger, level)("{} | {}", tag, event.message)
