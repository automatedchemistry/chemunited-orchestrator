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
    max_transport_substeps:
        Most pieces a step's transport may be cut into so that no flow moves
        more than a tube holds.  Hitting the limit logs one warning, and a tube
        overrun past it behaves as if it were longer until the flow slows.
    """

    dt: float = 0.1
    t_end: float | None = None
    real_time: bool = False
    viscosity: float = ETA_WATER_25C
    max_transport_substeps: int = 64
