"""Thread-safe singleton registry for the one active run."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

from chemunited_workflow.models import WorkflowExecutionEvent, WorkflowResult

_LOCKFILE_NAME = "run.lock"


class RunState(str, Enum):
    RUNNING = "running"
    PAUSED = "paused"
    FINISHED = "finished"
    FAILED = "failed"
    CANCELLED = "cancelled"


_ACTIVE_STATES = (RunState.RUNNING, RunState.PAUSED)


@dataclass
class RunRecord:
    run_id: str
    state: RunState = RunState.RUNNING
    cancel_event: threading.Event = field(default_factory=threading.Event)
    pause_event: threading.Event = field(default_factory=threading.Event)
    events: list[WorkflowExecutionEvent] = field(default_factory=list)
    results: list[WorkflowResult] = field(default_factory=list)
    pending_inputs: dict[str, threading.Event] = field(default_factory=dict)
    pending_input_messages: dict[str, str] = field(default_factory=dict)
    input_values: dict[str, str] = field(default_factory=dict)


class RunStore:
    """Thread-safe singleton registry for the one active run.

    Only one run can exist at a time (enforced by the physical platform).
    Call ``try_start`` to begin a run — it returns None if one is already active.
    All methods operate on the single active record; no run_id parameter needed.

    On startup, if a lockfile exists the store comes up RUNNING so the 409
    guard remains active after a crash or restart. The operator must call
    ``cancel`` to clear the stale lock.
    """

    def __init__(self, project_dir: Path | None = None) -> None:
        self._lock = threading.Lock()
        self._record: RunRecord | None = None
        self._project_dir = project_dir
        if project_dir is not None:
            self._restore_from_lockfile()

    def _lockfile_path(self) -> Path | None:
        if self._project_dir is None:
            return None
        return self._project_dir / _LOCKFILE_NAME

    def _restore_from_lockfile(self) -> None:
        lf = self._lockfile_path()
        if lf is None or not lf.exists():
            return
        try:
            data = json.loads(lf.read_text(encoding="utf-8"))
            run_id = data.get("run_id", "unknown")
        except Exception:
            run_id = "unknown"
        self._record = RunRecord(run_id=run_id, state=RunState.RUNNING)

    def _write_lockfile(self, run_id: str) -> None:
        lf = self._lockfile_path()
        if lf is None:
            return
        try:
            lf.write_text(
                json.dumps({"run_id": run_id, "state": "running"}),
                encoding="utf-8",
            )
        except OSError:
            pass

    def _delete_lockfile(self) -> None:
        lf = self._lockfile_path()
        if lf is None:
            return
        try:
            lf.unlink(missing_ok=True)
        except OSError:
            pass

    def set_project_dir(self, project_dir: Path) -> None:
        """Set the project directory for lockfile persistence (called on project load)."""
        with self._lock:
            self._project_dir = project_dir
        self._restore_from_lockfile()

    def try_start(self, protocol_filename: str) -> str | None:
        """Atomically start a new run. Returns the derived run_id, or None if busy."""
        with self._lock:
            if self._record is not None and self._record.state in _ACTIVE_STATES:
                return None
            stem = Path(protocol_filename).stem
            now = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
            run_id = f"{stem}_{now}"
            self._record = RunRecord(run_id=run_id)
        self._write_lockfile(run_id)
        return run_id

    def append_event(self, event: WorkflowExecutionEvent) -> None:
        with self._lock:
            if self._record is not None:
                self._record.events.append(event)

    def pop_events(self) -> list[WorkflowExecutionEvent]:
        """Return and clear all events accumulated since the last poll."""
        with self._lock:
            if self._record is None:
                return []
            events = list(self._record.events)
            self._record.events.clear()
            return events

    def append_result(self, result: WorkflowResult) -> None:
        with self._lock:
            if self._record is not None:
                self._record.results.append(result)

    def set_state(self, success: bool) -> None:
        with self._lock:
            if self._record is None:
                return
            if self._record.state == RunState.CANCELLED:
                self._delete_lockfile()
                return
            self._record.state = RunState.FINISHED if success else RunState.FAILED
        self._delete_lockfile()

    def get(self) -> RunRecord | None:
        with self._lock:
            return self._record

    def cancel_event(self) -> threading.Event | None:
        with self._lock:
            if self._record is None:
                return None
            return self._record.cancel_event

    def pause_event(self) -> threading.Event | None:
        with self._lock:
            if self._record is None:
                return None
            return self._record.pause_event

    def request_input(self, node_id: str, message: str) -> threading.Event:
        """Register a pending operator-input request for ``node_id`` and return its Event."""
        with self._lock:
            event = threading.Event()
            if self._record is not None:
                self._record.pending_inputs[node_id] = event
                self._record.pending_input_messages[node_id] = message
            return event

    def submit_input(self, node_id: str, value: str) -> bool:
        """Deliver an operator's reply for ``node_id``. Returns False if nothing is pending for it."""
        with self._lock:
            if self._record is None or node_id not in self._record.pending_inputs:
                return False
            self._record.input_values[node_id] = value
            self._record.pending_inputs[node_id].set()
            return True

    def pop_input_value(self, node_id: str) -> str | None:
        """Clear and return the delivered reply for ``node_id``, if any."""
        with self._lock:
            if self._record is None:
                return None
            self._record.pending_inputs.pop(node_id, None)
            self._record.pending_input_messages.pop(node_id, None)
            return self._record.input_values.pop(node_id, None)

    def pending_input_prompts(self) -> dict[str, str]:
        """Return ``{node_id: message}`` for every request awaiting an operator reply."""
        with self._lock:
            if self._record is None:
                return {}
            return dict(self._record.pending_input_messages)

    def cancel(self) -> bool:
        with self._lock:
            if self._record is None or self._record.state not in _ACTIVE_STATES:
                return False
            self._record.state = RunState.CANCELLED
            self._record.cancel_event.set()
            # Wake anything blocked in a pause checkpoint so it observes cancellation.
            self._record.pause_event.clear()
            # Wake anything blocked waiting on an operator reply, same reason.
            for event in self._record.pending_inputs.values():
                event.set()
        self._delete_lockfile()
        return True

    def pause(self) -> bool:
        with self._lock:
            if self._record is None or self._record.state != RunState.RUNNING:
                return False
            self._record.state = RunState.PAUSED
            self._record.pause_event.set()
        return True

    def resume(self) -> bool:
        with self._lock:
            if self._record is None or self._record.state != RunState.PAUSED:
                return False
            self._record.state = RunState.RUNNING
            self._record.pause_event.clear()
        return True

    @property
    def active_run_id(self) -> str | None:
        with self._lock:
            if self._record is not None and self._record.state in _ACTIVE_STATES:
                return self._record.run_id
            return None
