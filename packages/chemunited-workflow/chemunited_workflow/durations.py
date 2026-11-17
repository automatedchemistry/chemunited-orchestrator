"""Duration parsing helpers."""

from __future__ import annotations

import math
from datetime import timedelta

from chemunited_quantities import ureg

_TIMEOUT_COMMANDS_ERROR = (
    "timeout_commands must be a non-negative time duration like '10 s', "
    "or an empty string."
)

_DURATION_ERROR = (
    "A duration estimate must be a non-negative time such as '15 min' or "
    "'1.5 h', a number of seconds, a time quantity, or a timedelta."
)


def parse_timeout_commands(timeout_commands: str) -> float | None:
    """Return timeout duration in seconds, or ``None`` for no timeout."""
    if not isinstance(timeout_commands, str):
        raise ValueError("timeout_commands must be a string.")

    text = timeout_commands.strip()
    if text == "":
        return None

    try:
        seconds = float(ureg(text).to("second").magnitude)
    except Exception as exc:
        raise ValueError(_TIMEOUT_COMMANDS_ERROR) from exc

    if seconds < 0 or not math.isfinite(seconds):
        raise ValueError(_TIMEOUT_COMMANDS_ERROR)

    return seconds


def parse_duration(value: object) -> float | None:
    """Return a duration estimate in seconds, or ``None`` for no estimate.

    Accepts a string with a time unit (``"15 min"``, ``"1.5 h"``), a number
    of seconds, a time quantity (so ``volume / flow_rate`` works directly) or
    a :class:`~datetime.timedelta`. ``None`` and ``""`` mean no estimate.

    Raises ``ValueError`` for anything else, including a string without a
    unit (``"90"`` could mean seconds or minutes), a boolean, and a negative,
    infinite or non-time value.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(_DURATION_ERROR)
    if isinstance(value, (int, float)):
        seconds = float(value)
    elif isinstance(value, timedelta):
        seconds = value.total_seconds()
    elif isinstance(value, str):
        text = value.strip()
        if text == "":
            return None
        try:
            parsed = ureg(text)
        except Exception as exc:
            raise ValueError(_DURATION_ERROR) from exc
        seconds = _quantity_seconds(parsed)
    else:
        seconds = _quantity_seconds(value)

    if seconds < 0 or not math.isfinite(seconds):
        raise ValueError(_DURATION_ERROR)
    return seconds


def _quantity_seconds(value: object) -> float:
    """Convert a pint time quantity to seconds; reject anything else."""
    to = getattr(value, "to", None)
    if not callable(to):
        raise ValueError(_DURATION_ERROR)
    try:
        return float(to("second").magnitude)
    except Exception as exc:
        raise ValueError(_DURATION_ERROR) from exc
