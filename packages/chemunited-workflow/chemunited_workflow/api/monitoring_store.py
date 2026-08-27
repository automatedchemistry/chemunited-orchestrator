"""Thread-safe singleton registry for the one project-wide monitoring state."""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from ..exceptions import MonitoringRunActiveError

HISTORY_MAXLEN = 25


@dataclass
class MonitoringRecord:
    manual_on: bool = False
    run_active: bool = False
    recording: bool = False
    run_id: str | None = None
    stop_event: threading.Event = field(default_factory=threading.Event)
    latest: dict[str, dict[str, Any]] = field(default_factory=dict)
    history: dict[str, deque[dict[str, Any]]] = field(default_factory=dict)


class MonitoringStore:
    """Thread-safe singleton holder for the project's one monitoring state.

    There is no session id: monitoring is a single on/off toggle, forced on
    automatically while a protocol run is active (``run_active``), and
    reverting to whatever the manual toggle (``manual_on``) already was once
    the run ends. ``recording``/``run_id`` are set only while a run has opted
    in to persisting readings to disk; they never affect how values are
    fetched, only whether each tick is also written to a file.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._record = MonitoringRecord()

    @staticmethod
    def _raise_if_run_active(record: MonitoringRecord) -> None:
        if record.run_active:
            raise MonitoringRunActiveError(
                "Monitoring is running automatically for the active protocol run."
            )

    def raise_if_run_active(self) -> None:
        """Non-mutating check, callable by the service before other validation.

        Lets the service report 409 ahead of e.g. a 422 for missing config
        when both conditions hold — a run in progress means the manual
        endpoint isn't meaningful right now, regardless of what else is
        wrong with the request. try_manual_start()/try_manual_stop() re-check
        this under the same lock right before mutating, so a run starting in
        the gap between this call and theirs is still caught correctly.
        """
        with self._lock:
            self._raise_if_run_active(self._record)

    def try_manual_start(self) -> threading.Event | None:
        """Turn manual monitoring on.

        Returns the fresh stop_event for the caller to spawn a poll thread
        with, or None if monitoring was already on (no-op). Returning the
        event directly (rather than a bool the caller then fetches
        separately) keeps "create the event" and "hand it to the caller"
        one atomic step — no window where a concurrent begin_run() could
        observe an inconsistent state.

        Raises MonitoringRunActiveError if a protocol run currently has
        monitoring forced on — the manual toggle isn't the user's to use
        during a run.
        """
        with self._lock:
            self._raise_if_run_active(self._record)
            if self._record.manual_on:
                return None
            self._record.manual_on = True
            self._record.stop_event = threading.Event()
            return self._record.stop_event

    def try_manual_stop(self) -> None:
        """Turn manual monitoring off, signalling the poll thread to stop if one is running."""
        with self._lock:
            self._raise_if_run_active(self._record)
            if not self._record.manual_on:
                return
            self._record.manual_on = False
            self._record.stop_event.set()

    def begin_run(self, run_id: str, record: bool) -> threading.Event | None:
        """Force monitoring on for an active protocol run.

        Returns the fresh stop_event for the caller to spawn a poll thread
        with, if monitoring was previously off; None if a poll loop is
        already running and will pick up the new ``recording``/``run_id``
        on its next tick.
        """
        with self._lock:
            was_on = self._record.manual_on or self._record.run_active
            self._record.run_active = True
            self._record.recording = record
            self._record.run_id = run_id
            if was_on:
                return None
            self._record.stop_event = threading.Event()
            return self._record.stop_event

    def end_run(self) -> None:
        """Clear the run-forced state, stopping the poll thread unless the manual toggle is still on.

        The poll loop keeps running if the manual toggle was already on
        independently of the run — control simply reverts to whatever the
        user had set.
        """
        with self._lock:
            self._record.run_active = False
            self._record.recording = False
            self._record.run_id = None
            if not self._record.manual_on:
                self._record.stop_event.set()

    def poll_context(self) -> tuple[bool, str | None]:
        """Locked read of (recording, run_id) together, to avoid a torn read."""
        with self._lock:
            return self._record.recording, self._record.run_id

    def record_reading(self, key: str, reading: dict[str, Any]) -> None:
        with self._lock:
            self._record.latest[key] = reading
            self._record.history.setdefault(key, deque(maxlen=HISTORY_MAXLEN)).append(
                reading
            )

    def get_latest(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return dict(self._record.latest)

    def get_history(self, key: str) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._record.history.get(key, ()))

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            r = self._record
            return {
                "manual_on": r.manual_on,
                "run_active": r.run_active,
                "recording": r.recording,
                "run_id": r.run_id,
                "effective_on": r.manual_on or r.run_active,
            }
