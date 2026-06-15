from __future__ import annotations

import pytest
from chemunited_core.compounds import ChemicalEntity
from chemunited_core.utils import ChemUnitQuantity, ureg
from pytestqt.qtbot import QtBot

from chemunited.qt.elements.compounds import CompoundDialog
from chemunited.qt.elements.compounds.coolprop_lookup import (
    CoolPropLookupResult,
    lookup_compound_properties,
)
from chemunited.qt.shared.widgets.base_mode_editor._utils import units_for_dimension


def _magnitude(value, unit: str) -> float:
    return float(value.to(unit).magnitude)


def _dimensions(unit: str):
    return ureg.Quantity(1, unit).dimensionality


@pytest.mark.parametrize(
    ("unit", "expected"),
    [
        ("g/mol", ["g/mol", "kg/mol"]),
        ("J/(mol*K)", ["J/(mol*K)", "kJ/(mol*K)", "cal/(mol*K)"]),
        ("kg/m^3", ["kg/m^3", "g/cm^3", "g/ml"]),
    ],
)
def test_compound_property_units_are_curated(unit: str, expected: list[str]):
    assert units_for_dimension(_dimensions(unit), ureg) == expected


def test_lookup_compound_properties_fills_all_available_values():
    def props_si(output, input_1, value_1, input_2, value_2, fluid):
        assert fluid == "Water"
        values = {
            ("MOLARMASS", "", ""): 0.018015,
            ("CPMOLAR", "T|gas", "P"): 33.6,
            ("CPMOLAR", "T|liquid", "P"): 75.3,
            ("D", "T|liquid", "P"): 997.0,
        }
        return values[(output, input_1, input_2)]

    result = lookup_compound_properties("water", props_si=props_si)

    assert result.fluid_name == "Water"
    assert _magnitude(result.values["molecular_weight"], "g/mol") == pytest.approx(
        18.015
    )
    assert _magnitude(result.values["cp_gas"], "J/(mol*K)") == pytest.approx(33.6)
    assert _magnitude(result.values["cp_liquid"], "J/(mol*K)") == pytest.approx(75.3)
    assert _magnitude(result.values["density_liquid"], "kg/m^3") == pytest.approx(997)


def test_lookup_compound_properties_uses_ideal_gas_cp_fallback():
    def props_si(output, input_1, value_1, input_2, value_2, fluid):
        if output == "CPMOLAR" and input_1 == "T|gas":
            raise ValueError("gas state unavailable")
        values = {
            ("MOLARMASS", "", ""): 0.02897,
            ("CP0MOLAR", "T", "P"): 29.1,
        }
        return values[(output, input_1, input_2)]

    result = lookup_compound_properties("air", props_si=props_si)

    assert _magnitude(result.values["molecular_weight"], "g/mol") == pytest.approx(
        28.97
    )
    assert _magnitude(result.values["cp_gas"], "J/(mol*K)") == pytest.approx(29.1)
    assert "cp_liquid" not in result.values
    assert "density_liquid" not in result.values


def test_lookup_compound_properties_reports_missing_coolprop(monkeypatch):
    from chemunited.qt.elements.compounds import coolprop_lookup

    def raise_missing():
        raise ImportError("missing CoolProp")

    monkeypatch.setattr(coolprop_lookup, "_load_props_si", raise_missing)

    with pytest.raises(ImportError):
        lookup_compound_properties("water")


def test_compound_dialog_partial_lookup_does_not_overwrite_missing_fields(
    qtbot: QtBot,
    monkeypatch,
):
    from chemunited.qt.elements.compounds import compound_dialog

    dialog = CompoundDialog()
    qtbot.addWidget(dialog)

    cards = dialog.editor_widget._cards
    cards["name"].set_value("water")
    cards["cp_liquid"].set_value(ChemUnitQuantity("75.3 J/(mol*K)"))

    monkeypatch.setattr(dialog, "_show_success", lambda message: None)
    monkeypatch.setattr(dialog, "_show_warning", lambda message: None)
    monkeypatch.setattr(
        compound_dialog.coolprop_lookup,
        "lookup_compound_properties",
        lambda name: CoolPropLookupResult(
            "Water",
            {"molecular_weight": ChemUnitQuantity("18.015 g/mol")},
            {"cp_liquid": "unavailable"},
        ),
    )

    dialog._fill_from_coolprop()

    assert _magnitude(cards["molecular_weight"].get_value(), "g/mol") == pytest.approx(
        18.015
    )
    assert _magnitude(cards["cp_liquid"].get_value(), "J/(mol*K)") == pytest.approx(
        75.3
    )


def test_chemical_entity_quantity_defaults_use_nonblank_units(qtbot: QtBot):
    dialog = CompoundDialog()
    qtbot.addWidget(dialog)

    for field_name in ("molecular_weight", "cp_liquid", "cp_gas", "density_liquid"):
        card = dialog.editor_widget._cards[field_name]
        assert card._unit_combo.currentText()

    entity = ChemicalEntity()
    assert dialog.editor_widget._cards["molecular_weight"].get_value().to(
        "g/mol"
    ).magnitude == pytest.approx(entity.molecular_weight.to("g/mol").magnitude)
