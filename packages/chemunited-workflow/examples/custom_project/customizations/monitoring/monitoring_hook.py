"""Example custom monitoring sources for this project.

See docs/api-reference.md#custom-sources. Register a function name here under
`{"component": "custom", "command": "<name>", "kwargs": {...}}` in
connectivity/monitoring.json to poll it alongside the real devices — the poll
loop calls it with that variable's own `kwargs` on every tick and records
whatever it returns exactly like a real device reading.
"""

from __future__ import annotations

import random

from chemunited_workflow import MonitoringContext


def residence_time_min(flow_rate_ml_min: float, reactor_volume_ml: float) -> float:
    """Residence time (minutes) = reactor volume / flow rate.

    A *derived* reading: no device involved, just a formula over the
    variable's own kwargs (set in connectivity/monitoring.json). Useful for
    values that are a function of process parameters rather than something
    any single device reports directly.
    """
    return reactor_volume_ml / flow_rate_ml_min


def room_humidity_pct() -> float:
    """A purely synthetic reading with no formula and no device behind it —
    stands in for a sensor this project has no driver for yet, or a manual
    lab reading logged by some other means."""
    return round(random.uniform(38.0, 45.0), 1)


def chiller_temperature_f() -> float:
    """Fahrenheit reading derived from the real `chiller` component, read
    through MonitoringContext.platform — the same Platform (and its
    per-device lock) real-component readings use this ON-cycle, so this
    read shares that lock/connection instead of opening a second one.
    """
    platform = MonitoringContext.platform
    if platform is None:
        raise RuntimeError(
            "No poll cycle running: MonitoringContext.platform is unset."
        )
    celsius = platform["chiller"].get("temperature")
    return celsius * 9 / 5 + 32


def pre_process_bits() -> list[float]:
    platform = MonitoringContext.platform
    if platform is None:
        raise RuntimeError(
            "No poll cycle running: MonitoringContext.platform is unset."
        )
    channels = platform["Relay"].get("channels_set_point")
    return [i * 2.4 for i in channels]


CUSTOM_SOURCES = {
    "residence_time_min": residence_time_min,
    "room_humidity_pct": room_humidity_pct,
    "chiller_temperature_f": chiller_temperature_f,
    "pre_process_bits": pre_process_bits,
}
