"""Events a device client reports while it runs a command.

For each PUT/POST, the client reports ``started`` right before the request goes
out, then ``finished`` once its usual wait for the device to finish returns, or
``failed`` if the request fails or the wait times out. A client built with
``wait_for_completion=False`` (the dashboard's device panel) skips the wait and
reports ``finished`` as soon as the device accepts the command. GETs are not
reported. The events of one command share a ``call_id``. The live platform view
is built from these events; protocol code doesn't change.
"""

from __future__ import annotations

import itertools
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

CommandEventKind = Literal["started", "finished", "failed"]


@dataclass(frozen=True)
class CommandEvent:
    kind: CommandEventKind
    component: str
    command: str
    call_id: int = 0
    params: dict[str, Any] | None = None
    body: Any = None
    node: str | None = None
    error: str | None = None


CommandObserver = Callable[[CommandEvent], None]

_current = threading.local()
_call_ids = itertools.count(1)


def next_call_id() -> int:
    """A process-wide unique id for one command call."""
    return next(_call_ids)


def set_current_node(node: str | None) -> None:
    """Record the workflow node running on this thread (set by the executor)."""
    _current.node = node


def current_node() -> str | None:
    return getattr(_current, "node", None)
