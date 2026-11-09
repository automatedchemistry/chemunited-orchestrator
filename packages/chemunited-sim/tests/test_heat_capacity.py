"""Heat capacities are worked out once, but not across a project reload."""

from __future__ import annotations

import pytest

from chemunited_core.common.enums import PhaseKind
from chemunited_core.compounds import COMPOUNDS, ChemicalEntity
from chemunited_quantities import ChemUnitQuantity
from chemunited_sim.common.heat_capacity import molar_cp


def _compound(cp_liquid: float, cp_gas: float) -> ChemicalEntity:
    return ChemicalEntity(
        name="solvent",
        molecular_weight=ChemUnitQuantity("100 g/mol"),
        cp_liquid=ChemUnitQuantity(cp_liquid, "J/(mol*K)"),
        cp_gas=ChemUnitQuantity(cp_gas, "J/(mol*K)"),
        density_liquid=ChemUnitQuantity("1000 kg/m^3"),
    )


@pytest.fixture
def registry():
    COMPOUNDS.clear()
    yield COMPOUNDS
    COMPOUNDS.clear()


def test_reads_the_phase_it_is_asked_for(registry) -> None:
    registry.register(_compound(150.0, 90.0))

    assert molar_cp("solvent", PhaseKind.LIQUID) == pytest.approx(150.0)
    assert molar_cp("solvent", PhaseKind.GAS) == pytest.approx(90.0)


def test_a_reloaded_project_gets_its_own_values(registry) -> None:
    registry.register(_compound(150.0, 90.0))
    assert molar_cp("solvent", PhaseKind.LIQUID) == pytest.approx(150.0)

    registry.clear()
    registry.register(_compound(200.0, 90.0))

    assert molar_cp("solvent", PhaseKind.LIQUID) == pytest.approx(200.0)
