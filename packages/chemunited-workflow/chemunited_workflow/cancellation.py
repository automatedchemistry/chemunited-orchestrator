"""Cooperative cancellation helpers shared by device clients and Platform."""

from __future__ import annotations

import threading
import time

from .exceptions import OperatorInputTimeoutError, RunCancelledError


def raise_if_cancelled(cancellation_token: threading.Event | None) -> None:
    if cancellation_token is not None and cancellation_token.is_set():
        raise RunCancelledError("Run was cancelled.")


def wait_while_paused(
    pause_event: threading.Event | None,
    cancellation_token: threading.Event | None,
) -> None:
    """Block cooperatively while ``pause_event`` is set.

    Re-checks ``cancellation_token`` on every poll so a cancel issued while
    paused wakes the caller immediately instead of waiting out the hold.
    """
    if pause_event is None:
        return
    while pause_event.is_set():
        if cancellation_token is not None and cancellation_token.is_set():
            return
        pause_event.wait(timeout=0.1)


def sleep_interruptibly(
    duration: float,
    cancellation_token: threading.Event | None,
    pause_event: threading.Event | None = None,
) -> None:
    if duration <= 0:
        return
    if cancellation_token is None and pause_event is None:
        time.sleep(duration)
        return

    deadline = time.monotonic() + duration
    while True:
        if pause_event is not None and pause_event.is_set():
            paused_at = time.monotonic()
            wait_while_paused(pause_event, cancellation_token)
            # Time spent paused doesn't count against the wait duration.
            deadline += time.monotonic() - paused_at
        raise_if_cancelled(cancellation_token)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        timeout = min(remaining, 0.1)
        if cancellation_token is not None and cancellation_token.wait(timeout=timeout):
            raise RunCancelledError("Run was cancelled.")
        elif cancellation_token is None:
            time.sleep(timeout)


def wait_for_operator_input(
    event: threading.Event,
    cancellation_token: threading.Event | None,
    timeout_seconds: float,
) -> None:
    """Block cooperatively until ``event`` is set, the run is cancelled, or ``timeout_seconds`` elapses.

    Raises ``RunCancelledError`` if the run is cancelled while waiting, or
    ``OperatorInputTimeoutError`` if no reply arrives before the deadline.

    A cancellation also wakes ``event`` (see ``RunStore.cancel``) so a blocked
    wait doesn't sit out the rest of its timeout — the cancellation check runs
    first on every loop pass so that wake-up is never mistaken for a real reply.
    """
    deadline = time.monotonic() + timeout_seconds
    while True:
        raise_if_cancelled(cancellation_token)
        if event.is_set():
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise OperatorInputTimeoutError(
                f"No operator reply received within {timeout_seconds} second(s)."
            )
        event.wait(timeout=min(remaining, 0.1))
