"""Simulation configuration for the worker module."""

from __future__ import annotations

from dataclasses import dataclass

from ..common.constant import ETA_WATER_25C


@dataclass
class SimConfig:
    """Parameters that govern one simulation run.

    Attributes
    ----------
    dt:
        Simulation time step in seconds.
    t_end:
        Simulation end time in seconds.  The worker runs from t=0 to t=t_end
        inclusive.  When ``None`` in mode 1 (workflow), the server worker
        auto-completes as soon as the workflow finishes and all queues are empty.
    viscosity:
        Dynamic viscosity of the carrier fluid in Pa·s.  Defaults to water
        at 25 °C (8.9 × 10⁻⁴ Pa·s).
    """

    dt: float = 0.1
    t_end: float | None = None
    real_time: bool = False
    viscosity: float = ETA_WATER_25C
