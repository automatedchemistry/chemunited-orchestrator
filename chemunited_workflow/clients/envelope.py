"""Normalized response envelope shared by every transport-specific client."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class CommandResponse:
    """Transport-agnostic result of a single get/put/post call.

    ``body_fn`` is a zero-arg callable rather than an eagerly computed value:
    today's HTTP client only calls ``resp.json()`` after the post-command
    wait/feedback-poll has run, so a malformed body only ever surfaces after
    that wait. Eagerly decoding here would reorder that surfacing relative to
    the wait — keeping it lazy preserves the existing behavior exactly.
    """

    native: Any
    text: str
    body_fn: Callable[[], Any]
