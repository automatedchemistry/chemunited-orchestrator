import pytest
from pydantic import ValidationError

from chemunited_core.common.enums import PhaseKind
from chemunited_core.compounds import (
    COMPOUNDS,
    ChemicalEntity,
    Compounds,
    VolumeContentBase,
)
from chemunited_quantities import (
    ChemUnitQuantity,
    units_for_dimension,
    ureg,
)


def _dimensions(unit: str):
    return ureg.Quantity(1, unit).dimensionality


@pytest.mark.parametrize(
    ("unit", "expected"),
    [
        ("g/mol", ["g/mol", "kg/mol"]),
        ("J/(mol*K)", ["J/(mol*K)", "kJ/(mol*K)", "cal/(mol*K)"]),
        ("kg/m^3", ["kg/m^3", "g/cm^3", "g/ml"]),
        ("rpm", ["rpm"]),
    ],
)
def test_quantity_units_for_curated_dimensions(unit: str, expected: list[str]) -> None:
    assert units_for_dimension(_dimensions(unit), ureg) == expected


def test_quantity_units_for_none_dimension() -> None:
    assert units_for_dimension(None, ureg) == []


def test_quantity_units_for_uncurated_dimension() -> None:
    units = units_for_dimension(_dimensions("m/s^2"), ureg)

    assert len(units) == 1
    assert ureg.Quantity(1, units[0]).dimensionality == _dimensions("m/s^2")


def test_chemical_entity_default_air_values() -> None:
    entity = ChemicalEntity()

    assert entity.name == "air"
    assert entity.molecular_weight == ChemUnitQuantity("28.97 g/mol")
    assert entity.cp_gas == ChemUnitQuantity("29.1 J/(mol*K)")
    assert entity.cp_liquid == ChemUnitQuantity("0 J/(mol*K)")
    assert entity.density_liquid == ChemUnitQuantity("0 kg/m^3")
    assert entity.color == "#00000000"
    assert entity.color_red == 0
    assert entity.color_green == 0
    assert entity.color_blue == 0
    assert entity.color_alpha == 255


def test_chemical_entity_accepts_unit_strings() -> None:
    entity = ChemicalEntity(
        name="water",
        molecular_weight="18.015 g/mol",
        cp_liquid="75.3 J/(mol*K)",
        cp_gas="33.6 J/(mol*K)",
        density_liquid="997 kg/m^3",
    )

    assert entity.molecular_weight == ChemUnitQuantity("18.015 g/mol")
    assert entity.cp("liquid") == ChemUnitQuantity("75.3 J/(mol*K)")
    assert entity.cp("gas") == ChemUnitQuantity("33.6 J/(mol*K)")
    assert entity.molar_volume_liquid().check("[length] ** 3 / [substance]")


def test_chemical_entity_accepts_bare_numeric_quantities_with_default_units() -> None:
    entity = ChemicalEntity(
        molecular_weight=18.015,
        cp_liquid=75.3,
        cp_gas=33.6,
        density_liquid=997,
    )

    assert entity.molecular_weight == ChemUnitQuantity("18.015 g/mol")
    assert entity.cp_liquid == ChemUnitQuantity("75.3 J/(mol*K)")
    assert entity.cp_gas == ChemUnitQuantity("33.6 J/(mol*K)")
    assert entity.density_liquid == ChemUnitQuantity("997 kg/m^3")


@pytest.mark.parametrize(
    "field,value",
    [
        ("molecular_weight", "-1 g/mol"),
        ("cp_liquid", "-1 J/(mol*K)"),
        ("cp_gas", "-1 J/(mol*K)"),
        ("density_liquid", "-1 kg/m^3"),
    ],
)
def test_chemical_entity_rejects_invalid_quantities(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        ChemicalEntity(**{field: value})


@pytest.mark.parametrize(
    "field,value",
    [("color_red", -1), ("color_green", 256), ("color_alpha", 256)],
)
def test_chemical_entity_rejects_invalid_rgb_channels(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        ChemicalEntity(**{field: value})


def test_chemical_entity_color_property_and_hex_helpers_are_separate() -> None:
    entity = ChemicalEntity(
        color_red=17,
        color_green=34,
        color_blue=51,
        color_alpha=68,
    )

    assert entity.rgb_hex == "#112233"
    assert entity.rgba_hex == "#11223344"

    entity.color = "#11223344"

    assert entity.color == "#11223344"
    assert entity.rgb_hex == "#112233"
    assert entity.rgba_hex == "#11223344"


def test_chemical_entity_dump_includes_rgb_but_not_internal_color() -> None:
    entity = ChemicalEntity(color_red=1, color_green=2, color_blue=3)
    entity.color = "#01020344"

    dumped = entity.model_dump()

    assert dumped["color_red"] == 1
    assert dumped["color_green"] == 2
    assert dumped["color_blue"] == 3
    assert dumped["color_alpha"] == 255
    assert "color" not in dumped
    assert "_color" not in dumped


def test_chemical_entity_default_air_phase_methods() -> None:
    entity = ChemicalEntity()

    assert entity.cp("gas") == ChemUnitQuantity("29.1 J/(mol*K)")
    assert entity.molar_volume_gas(temperature=298.15, pressure=101325).check(
        "[length] ** 3 / [substance]"
    )

    with pytest.raises(ValueError, match="cp_liquid is not defined"):
        entity.cp("liquid")
    with pytest.raises(ValueError, match="density_liquid is not defined"):
        entity.molar_volume_liquid()
    with pytest.raises(ValueError, match="Unknown phase"):
        entity.cp("solid")


def test_compounds_registry_restores_default_air() -> None:
    COMPOUNDS.register(ChemicalEntity(name="argon", molecular_weight="39.948 g/mol"))
    assert "argon" in COMPOUNDS

    COMPOUNDS.clear()

    assert "argon" not in COMPOUNDS
    assert COMPOUNDS["air"].name == "air"
    assert COMPOUNDS["air"].color == "#00000000"


def test_compounds_get_color_returns_transparent_for_empty_or_air_gas() -> None:
    registry = Compounds()

    assert registry.get_color(VolumeContentBase()) == "#FFFFFF00"
    assert (
        registry.get_color(
            VolumeContentBase(
                phase_kind=PhaseKind.GAS,
                volume=1.0,
                initial_species={"air": 41.0},
            )
        )
        == "#FFFFFF00"
    )


def test_compounds_get_color_uses_half_opacity_for_visible_gas() -> None:
    registry = Compounds()
    registry.register(ChemicalEntity(name="argon", color_red=255))

    color = registry.get_color(
        VolumeContentBase(
            phase_kind=PhaseKind.GAS,
            initial_species={"air": 10.0, "argon": 2.0},
        )
    )

    assert color == "#FF000080"


def test_compounds_get_color_uses_full_opacity_for_liquid_mixture() -> None:
    registry = Compounds()
    registry.register(ChemicalEntity(name="red", color_red=255))
    registry.register(ChemicalEntity(name="green", color_green=255))

    color = registry.get_color(
        VolumeContentBase(
            phase_kind=PhaseKind.LIQUID,
            initial_species={"red": 1.0, "green": 1.0},
        )
    )

    assert color == "#808000FF"


def test_compounds_get_color_ignores_unknown_with_visible_species() -> None:
    registry = Compounds()
    registry.register(ChemicalEntity(name="blue", color_blue=255))

    color = registry.get_color(
        VolumeContentBase(
            phase_kind=PhaseKind.LIQUID,
            initial_species={"unknown": 100.0, "blue": 1.0},
        )
    )

    assert color == "#0000FFFF"


def test_compounds_get_color_returns_transparent_for_only_unknown_species() -> None:
    registry = Compounds()

    color = registry.get_color(
        VolumeContentBase(
            phase_kind=PhaseKind.LIQUID,
            initial_species={"unknown": 1.0},
        )
    )

    assert color == "#FFFFFF00"


def test_compounds_get_color_rejects_unknown_phase() -> None:
    registry = Compounds()

    with pytest.raises(ValueError, match="Unknown phase"):
        registry.get_color(VolumeContentBase(phase_kind="solid"))
