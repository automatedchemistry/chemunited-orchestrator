"""Duration parsing helpers."""

from __future__ import annotations

import math

from chemunited_quantities import ureg

_TIMEOUT_COMMANDS_ERROR = (
    "timeout_commands must be a non-negative time duration like '10 s', "
    "or an empty string."
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
