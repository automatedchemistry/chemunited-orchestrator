"""Junction pocket-merging logic for chemunited-sim transport.

Called by the transport engine when pockets arrive at a hub node.
Same-phase pockets are merged into one using ideal mixing rules:
volume-weighted temperature, summed species moles.
Different phases produce separate merged pockets.
"""

from __future__ import annotations

from collections import defaultdict

from chemunited_core.common.enums import PhaseKind

from ..common.constant import MIN_POCKET_VOLUME
from .models import Pocket


def merge_arriving_pockets(pockets: list[Pocket]) -> list[Pocket]:
    """Merge a list of arriving pockets into at most one pocket per phase.

    Rules (Version-1 frozen):

    - Same phase: sum volumes, sum species moles, volume-weighted mean
      temperature and pressure.
    - Different phases: keep as separate merged pockets (no interphase
      mixing).
    - Pockets below :data:`~chemunited_sim.common.constant.MIN_POCKET_VOLUME`
      after merging are discarded.

    Parameters
    ----------
    pockets:
        All pockets that arrived at a hub node this step.

    Returns
    -------
    list[Pocket]
        Zero, one, or two merged pockets (one per phase present).
    """
    by_phase: dict[PhaseKind, list[Pocket]] = defaultdict(list)
    for p in pockets:
        by_phase[p.phase_kind].append(p)

    result: list[Pocket] = []
    for phase_kind, group in by_phase.items():
        total_volume = sum(p.volume for p in group)
        if total_volume < MIN_POCKET_VOLUME:
            continue

        # Volume-weighted mean temperature and pressure
        temperature = sum(p.temperature * p.volume for p in group) / total_volume
        pressure = sum(p.pressure * p.volume for p in group) / total_volume

        # Sum species moles
        species: dict[str, float] = {}
        for p in group:
            for sp, mol in p.species_moles.items():
                species[sp] = species.get(sp, 0.0) + mol

        result.append(
            Pocket(
                phase_kind=phase_kind,
                volume=total_volume,
                species_moles=species,
                temperature=temperature,
                pressure=pressure,
            )
        )

    return result
