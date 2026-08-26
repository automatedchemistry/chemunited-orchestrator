"""Simulation-specific constants for chemunited-sim.

Physical constants shared with chemunited-core are re-exported here for
convenience.  Solver-specific tunables (epsilon values, defaults) are
defined here and nowhere else — never redefine them inline in solver code.
"""

from chemunited_core.common.constant import (  # noqa: F401
    AMBIENT_TEMPERATURE_K,
    ATMOSPHERE_PRESSURE_PA,
    R_MAX_HYDRAULIC,
)

# ---------------------------------------------------------------------------
# Hydraulic solver tunables
# ---------------------------------------------------------------------------

# Epsilon resistance for JUNCTION-role edges.  Keeps the admittance matrix
# well-conditioned while imposing negligible pressure drop.  Unit: Pa·s/m³.
R_JUNCTION: float = 1e3

# Default dynamic viscosity for water at 25 °C.  Unit: Pa·s.
ETA_WATER_25C: float = 8.9e-4

# Magnitude threshold (Pa, relative to atmospheric) beyond which a solved
# node pressure is considered physically implausible for a real hydraulic
# network and is surfaced as a WARNING (not raised - see hydraulics.solver
# module docstring). Sized generously above realistic lab operating
# pressures - BPR/back-pressure setpoints and gas supplies in example
# platforms top out around 1-3 bar - while still catching genuine
# numerical blow-ups. Unit: Pa.
PRESSURE_SANITY_THRESHOLD_PA: float = 1.0e7  # ~100 bar

# ---------------------------------------------------------------------------
# Transport module constants
# ---------------------------------------------------------------------------

# Pockets whose volume falls below this threshold are discarded at the end
# of each transport step to prevent accumulation of floating-point fragments.
# Unit: m³.
MIN_POCKET_VOLUME: float = 1e-18

# Tolerance for _fill_carrier_deficits' "is this edge genuinely underfilled"
# check. Deliberately separate from MIN_POCKET_VOLUME, which is tuned to
# discard floating-point fragments, not to validate them - reusing it here
# let ordinary summation drift from repeated pocket splitting get promoted
# into permanent synthetic air pockets every tick. Unit: m³ / fraction.
DEFICIT_FILL_ABS_TOL: float = 1e-12
DEFICIT_FILL_REL_TOL: float = 1e-6

# Safety limit on the number of JUNCTION hops a pocket may traverse in a
# single step.  Guards against degenerate graph topologies with cycles.
MAX_JUNCTION_HOPS: int = 32

# ---------------------------------------------------------------------------
# Reactions module constants
# ---------------------------------------------------------------------------

# Species with moles below this threshold are treated as absent by reaction
# step methods.  Prevents division-by-zero and negative-mole drift from
# floating-point rounding when a species is nearly consumed.  Unit: mol.
MIN_REACTION_MOLES: float = 1e-30

# ---------------------------------------------------------------------------
# Recorder module constants
# ---------------------------------------------------------------------------

# Default simulation time step.  Unit: s.
RECORDER_DT_DEFAULT: float = 0.1

# Default record interval (how often state is written to SQLite).  Unit: s.
RECORDER_INTERVAL_DEFAULT: float = 2.0

# Nominal cell length used when slicing TRANSPORT edges into fixed-length
# cells for the recorder.  The last cell in each edge absorbs any remainder.
# Shorter values give finer spatial resolution at the cost of more rows.
# Unit: m.
RECORDER_CELL_LENGTH_M: float = 0.01
