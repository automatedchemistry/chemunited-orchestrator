"""Project-scoped tailer for `<project_dir>/log/pool/*.jsonl`.

Lives for as long as a project is loaded, so it covers command activity that
has no HTTP polling loop of its own (the standalone "Simulate" flow in
chemunited.simulation.simulate_report). It must NOT run while a full
execution is active: the workflow API server drains and deletes these same
files server-side during a run (see OrchestratorExecution._on_pool_drained),
and a second reader opening those files at the same time can make the
server's own delete fail on Windows (a plain open() doesn't set
share-delete). That flow is covered separately via the already-emitted
RunPollingThread.pool_drained signal.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from loguru import logger
from PyQt5.QtCore import QObject, QTimer

from chemunited.elements.access import Components
from chemunited.elements.pool_commands import apply_pool_command

INTERVAL_MS = 400
_DRAINING_SUFFIX = ".draining"


class PoolLogTailer(QObject):
    def __init__(
        self,
        project_dir: Path | str,
        components: Components,
        is_run_active: Callable[[], bool],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._pool_dir = Path(project_dir) / "log" / "pool"
        self._components = components
        self._is_run_active = is_run_active
        self._cleaned_initial = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        self._cleaned_initial = False
        self._timer.start(INTERVAL_MS)

    def stop(self) -> None:
        self._timer.stop()
        self._cleaned_initial = False

    def _tick(self) -> None:
        if self._is_run_active():
            return
        if not self._pool_dir.is_dir():
            return

        files = sorted(self._pool_dir.glob("*.jsonl"))

        if not self._cleaned_initial:
            # Pre-existing content is leftover from a previous session (or the
            # execution flow, which already visualized it live) - clean it up
            # without replaying it as if it just happened.
            for path in files:
                self._drain_file(path, apply=False)
            self._cleaned_initial = True
            return

        for path in files:
            self._drain_file(path, apply=True)

    def _drain_file(self, path: Path, *, apply: bool) -> None:
        # Rename-then-read rather than read-then-truncate in place: the writer
        # (device client / simulator) always re-opens the file by path per
        # command (open-append-close), so once we've renamed path away, our
        # copy is exclusively ours - no read/truncate race with new appends.
        draining_path = path.with_name(path.name + _DRAINING_SUFFIX)
        try:
            path.rename(draining_path)
        except OSError:
            return  # transiently locked/already gone; retry next tick

        try:
            content = draining_path.read_bytes()
        except OSError:
            return
        finally:
            try:
                draining_path.unlink()
            except OSError:
                pass

        if not apply:
            return

        for line in content.splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                logger.debug(f"Skipping malformed pool log line in {path.name}")
                continue
            apply_pool_command(self._components, entry)
