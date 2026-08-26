"""Stateful time-scrubbing session for a chemunited-sim recording database.

Keeps one read-only sqlite3 connection open for the lifetime of a scrubbing
session (instead of reopening it on every drag tick) and exposes the sorted
list of recorded snapshot instants, so callers can map slider integer
positions directly onto exact recorded timestamps - index-based, no
snapping or interpolation.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from loguru import logger

from chemunited.elements.access import Components, Connections

from .final_state import apply_simulation_state_at, list_recorded_times


class SimulationPlayback:
    """One open read-only connection plus the sorted recorded times for a run."""

    def __init__(
        self, db_path: Path, conn: sqlite3.Connection, times: list[float]
    ) -> None:
        self.db_path = db_path
        self._conn = conn
        self.times = times

    @classmethod
    def open(cls, db_path: Path) -> "SimulationPlayback | None":
        """Open *db_path* read-only and load its recorded times, or None on failure."""
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
        except sqlite3.Error as exc:
            logger.warning(
                f"Could not open simulation DB '{db_path}' for playback: {exc}"
            )
            return None
        return cls(db_path, conn, list_recorded_times(conn))

    @property
    def frame_count(self) -> int:
        return len(self.times)

    def apply_at_time(
        self, t: float, components: Components, connections: Connections
    ) -> None:
        """Render the recorded snapshot at exactly *t* onto the canvas."""
        try:
            apply_simulation_state_at(self._conn, t, components, connections)
        except Exception:
            logger.opt(exception=True).warning(
                f"Failed to apply simulation state at t={t} from '{self.db_path}'"
            )

    def close(self) -> None:
        self._conn.close()
