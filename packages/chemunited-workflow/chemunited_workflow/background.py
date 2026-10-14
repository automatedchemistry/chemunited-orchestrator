"""Run-scoped host for background workflow nodes.

A background node (``block_tag="background"``) runs detached from its
process: the workflow never waits for it, so the protocol moves on to the
next process while it keeps running. It is stopped by the run's
cancellation token, which ``RunnerService`` trips once the protocol ends.
"""

from __future__ import annotations

import threading
import time
from typing import Callable

# How long the run waits for background nodes to return after signalling
# them to stop, before abandoning them (they are daemon threads).
STOP_TIMEOUT_SECONDS = 10.0


class BackgroundTasks:
    """Tracks the threads of every background node started during one run."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._threads: list[threading.Thread] = []

    @property
    def has_tasks(self) -> bool:
        with self._lock:
            return bool(self._threads)

    def submit(self, fn: Callable[[], None], name: str) -> None:
        thread = threading.Thread(target=fn, name=f"background-{name}", daemon=True)
        with self._lock:
            self._threads.append(thread)
        thread.start()

    def join(self, timeout: float) -> list[str]:
        """Wait up to ``timeout`` seconds in total for every thread to finish.

        Returns the names of threads still alive afterwards — background
        nodes that ignored the stop signal. They are daemon threads, so they
        never keep the interpreter alive.
        """
        with self._lock:
            threads = list(self._threads)
        deadline = time.monotonic() + timeout
        for thread in threads:
            thread.join(max(0.0, deadline - time.monotonic()))
        return [thread.name for thread in threads if thread.is_alive()]
