"""Hydraulic solver output model and exception.

``HydraulicState`` is the immutable result of one hydraulic solve.
``HydraulicSolveError`` is raised when the solver cannot produce a valid result.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HydraulicState:
    """Snapshot of pressures and volumetric flows after one hydraulic solve.

    Produced by :func:`~chemunited_sim.hydraulics.solver.solve` and consumed
    by the transport module to determine pocket displacement each time step.

    Attributes
    ----------
    pressures:
        Mapping from ``node_id`` to absolute pressure in Pa.
    flows:
        Mapping from ``edge_id`` to volumetric flow rate in m³/s.
        Sign convention: positive = flow from origin node to destination
        node; negative = flow in the reverse direction.
    """

    pressures: dict[str, float]
    flows: dict[str, float]


class HydraulicSolveError(RuntimeError):
    """Raised when the hydraulic solver cannot produce a valid result.

    Possible causes:
    - A TRANSPORT edge has zero or negative diameter.
    - The underlying linear system is singular despite the atmospheric
      anchor (structurally degenerate graph).
    """
