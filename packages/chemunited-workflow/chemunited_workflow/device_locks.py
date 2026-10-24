"""One lock per device, shared by every ``Platform`` in the process.

The run, the monitoring service and manual dashboard commands each build their
own ``Platform`` (and so their own client objects), but they talk to the same
devices. Serial instruments behind an HTTP wrapper can corrupt an exchange when
two requests reach them at once, so every request to a device takes that
device's lock first — the request only, never a whole command: a pump infusing
for ten minutes still answers monitoring reads between the idle-wait polls.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

from .exceptions import DeviceBusyError

DEVICE_LOCK_TIMEOUT_SECONDS = 10.0

_locks: dict[str, threading.Lock] = {}
_registry_lock = threading.Lock()


def device_lock(key: str) -> threading.Lock:
    """Return the process-wide lock for the device identified by *key*."""
    with _registry_lock:
        lock = _locks.get(key)
        if lock is None:
            lock = _locks[key] = threading.Lock()
        return lock


@contextmanager
def hold_device(key: str, timeout: float | None = None) -> Iterator[None]:
    """Hold *key*'s device lock for one request.

    Raises ``DeviceBusyError`` if another request to the same device didn't
    finish within *timeout* seconds (default ``DEVICE_LOCK_TIMEOUT_SECONDS``).
    """
    if timeout is None:
        timeout = DEVICE_LOCK_TIMEOUT_SECONDS
    lock = device_lock(key)
    if not lock.acquire(timeout=timeout):
        raise DeviceBusyError(
            f"Device {key!r} is busy: another request to it did not finish "
            f"within {timeout:g} s."
        )
    try:
        yield
    finally:
        lock.release()
