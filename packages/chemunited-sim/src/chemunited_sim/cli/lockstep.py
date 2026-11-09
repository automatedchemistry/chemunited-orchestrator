"""Lockstep between a run's workflow threads and its physics thread.

Left to run freely, the two race: physics keeps stepping while a node is between
commands, so how long a valve really stays open depends on thread scheduling.
Here physics steps only while every running node is parked on a simulated wait
and none of those waits is due, and a node only runs while physics is parked. The
two never touch state at once, and repeat runs come out identical.

One limit: while a background node is parked, physics can take a step in the
moment between two processes, when nothing else is running. Such a run can shift
by a step between repeats.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator, Sequence
from concurrent.futures import Future
from contextlib import contextmanager
from typing import Any

from loguru import logger

from chemunited_workflow import (
    RunCancelledError,
    WorkflowEventType,
    WorkflowExecutionEvent,
    WorkflowExecutor,
)

from .clock import SimClock

# A node should reach its next simulated wait almost at once. One that takes this
# many seconds, say with a time.sleep() in a protocol, is relying on physics moving
# on regardless, so physics goes back to running freely rather than hang the run.
STALL_SECONDS = 60.0

_TIME_EPS = 1e-9
_POLL_SECONDS = 0.25


class Lockstep:
    """Hands control back and forth between a run's workflow and its physics."""

    def __init__(
        self,
        clock: SimClock,
        stop_event: threading.Event,
        stall_seconds: float = STALL_SECONDS,
    ) -> None:
        self._clock = clock
        self._stop = stop_event
        self._stall_seconds = stall_seconds
        self._cv = threading.Condition()
        self._waiters: dict[int, float] = {}
        self._running_nodes: set[tuple[str | None, Any]] = set()
        self._holds = 0
        self._finished = False
        self._free_running = False

    @property
    def free_running(self) -> bool:
        """Whether a stalled node made physics give up waiting for the workflow."""
        return self._free_running

    # -- Workflow side ---------------------------------------------------------

    def wait_until(self, deadline: float) -> None:
        """Park the calling thread until the simulated *deadline*."""
        thread = threading.get_ident()
        with self._cv:
            self._waiters[thread] = deadline
            self._cv.notify_all()
            try:
                while self._clock.now() < deadline - _TIME_EPS:
                    if self._stop.is_set():
                        raise RunCancelledError("Run was cancelled.")
                    self._cv.wait(_POLL_SECONDS)
                if self._stop.is_set():
                    raise RunCancelledError("Run was cancelled.")
            finally:
                del self._waiters[thread]
                self._cv.notify_all()

    def on_event(self, event: WorkflowExecutionEvent) -> None:
        """Keep count of the running nodes, from the executor's own events."""
        node = (event.process, event.node_key)
        with self._cv:
            if event.event_type == WorkflowEventType.NODE_RUNNING:
                self._running_nodes.add(node)
            elif event.event_type in (
                WorkflowEventType.NODE_COMPLETED,
                WorkflowEventType.NODE_FAILED,
            ):
                self._running_nodes.discard(node)
            self._cv.notify_all()

    @contextmanager
    def hold(self) -> Iterator[None]:
        """Keep physics parked for the duration, however parked the nodes are."""
        with self._cv:
            self._holds += 1
        try:
            yield
        finally:
            with self._cv:
                self._holds -= 1
                self._cv.notify_all()

    def finish(self) -> None:
        """The workflow is done: physics has nothing left to wait for."""
        with self._cv:
            self._finished = True
            self._cv.notify_all()

    # -- Physics side ----------------------------------------------------------

    def park_physics(self) -> bool:
        """Block until physics may take a step. False means the run is over."""
        give_up = time.monotonic() + self._stall_seconds
        with self._cv:
            while True:
                if self._finished or self._stop.is_set():
                    return False
                if self._free_running or self._may_step():
                    return True
                remaining = give_up - time.monotonic()
                if remaining <= 0.0:
                    self._free_running = True
                    logger.warning(
                        "lockstep: a workflow node ran for {:.0f} s without a "
                        "simulated wait, for example a time.sleep() in a protocol. "
                        "Physics now runs freely, so timings in this run aren't exact.",
                        self._stall_seconds,
                    )
                    return True
                self._cv.wait(min(remaining, _POLL_SECONDS))

    def stepped(self) -> None:
        """Physics advanced the clock: wake any wait that has come due."""
        with self._cv:
            self._cv.notify_all()

    def _may_step(self) -> bool:
        if self._holds or not self._waiters:
            return False
        if len(self._waiters) < len(self._running_nodes):
            return False
        soonest = min(self._waiters.values())
        return self._clock.now() < soonest - _TIME_EPS


class LockstepExecutor(WorkflowExecutor):
    """A WorkflowExecutor that keeps a :class:`Lockstep` informed.

    Physics stays parked while this works out what runs next after a node, so a
    node started by that decision starts at the same simulated time on every run.
    """

    def __init__(
        self,
        compiled_workflow: Any,
        *,
        lockstep: Lockstep,
        event_listeners: Sequence[Any] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            compiled_workflow,
            event_listeners=[lockstep.on_event, *(event_listeners or ())],
            **kwargs,
        )
        self._lockstep = lockstep

    def _handle_completed_future(self, node_key: Any, future: Future[Any]) -> None:
        with self._lockstep.hold():
            super()._handle_completed_future(node_key, future)
