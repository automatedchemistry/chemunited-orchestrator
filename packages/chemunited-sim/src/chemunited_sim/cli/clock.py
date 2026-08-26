"""Shared simulation clock — thread-safe monotonic counter."""

from __future__ import annotations

import threading


class SimClock:
    """Thread-safe simulation clock shared between Worker and Workflow threads."""

    def __init__(self) -> None:
        self._t: float = 0.0
        self._lock = threading.Lock()

    def now(self) -> float:
        with self._lock:
            return self._t

    def advance(self, dt: float) -> None:
        with self._lock:
            self._t += dt

    def reset(self) -> None:
        with self._lock:
            self._t = 0.0
