"""Molar heat capacities as plain numbers, for code that runs every step.

Going through unit conversion for each species on every arrival is slow enough to
show in a run's speed. A compound's properties don't change during a run, so each
value is worked out once. The cache holds the compound itself, so a project reload
that registers a new one under the same name gets a new entry.
"""

from __future__ import annotations

from chemunited_core.common.enums import PhaseKind
from chemunited_core.compounds import COMPOUNDS, ChemicalEntity

_CACHE: dict[tuple[int, PhaseKind], tuple[ChemicalEntity, float]] = {}


def molar_cp(species_id: str, phase: PhaseKind) -> float:
    """Molar heat capacity of a registered compound in J/(mol*K)."""
    entity = COMPOUNDS[species_id]
    key = (id(entity), phase)
    cached = _CACHE.get(key)
    if cached is None:
        phase_name = "liquid" if phase == PhaseKind.LIQUID else "gas"
        cached = (entity, float(entity.cp(phase_name).to_base_units().magnitude))
        _CACHE[key] = cached
    return cached[1]
