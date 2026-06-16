from __future__ import annotations

from types import SimpleNamespace

import pytest
from chemunited_core.compounds import COMPOUNDS, ChemicalEntity
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFrame
from pytestqt.qtbot import QtBot

from chemunited.elements.component import create_component
from chemunited.elements.compounds import CompoundDialog, CompoundList, CompoundsWidget
from chemunited.elements.compounds.compound_list import _swatch_stylesheet
from chemunited.elements.compounds.iventory_status import (
    InventoryStatusDialog,
    InventoryStatusWidget,
)
from chemunited.setup import SetupWindow


def _magnitude(value, unit: str) -> float:
    return float(value.to(unit).magnitude)


@pytest.fixture(autouse=True)
def reset_compounds():
    COMPOUNDS.clear()
    yield
    COMPOUNDS.clear()


@pytest.fixture
def compound_list(qtbot: QtBot) -> CompoundList:
    widget = CompoundList()
    qtbot.addWidget(widget)
    widget.show()
    qtbot.waitExposed(widget)
    return widget


class _FakeDialog:
    def __init__(self, *, parent=None, accepted=True, entity=None):
        self.parent = parent
        self.accepted = accepted
        self.entity = entity

    def exec_(self):
        return self.accepted

    def get_result_instance(self):
        return self.entity


def _patch_dialog(monkeypatch, *, accepted=True, entity=None) -> None:
    def factory(parent=None):
        return _FakeDialog(parent=parent, accepted=accepted, entity=entity)

    monkeypatch.setattr(
        "chemunited.elements.compounds.compound_list.CompoundDialog",
        factory,
    )


def test_initial_list_contains_registered_compounds(compound_list: CompoundList):
    assert compound_list.visible_names() == ["air"]


def test_rows_include_color_swatch(compound_list: CompoundList):
    COMPOUNDS.register(
        ChemicalEntity(
            name="water",
            molecular_weight=18.015,
            color_red=0x33,
            color_green=0x66,
            color_blue=0xFF,
            color_alpha=255,
        )
    )

    compound_list.sync()

    assert compound_list.visible_names() == ["air", "water"]
    row = compound_list.list_widget.itemWidget(compound_list.list_widget.item(1))
    assert row is not None
    assert row.findChild(QFrame, "compound-color-swatch") is not None
    assert compound_list.list_widget.item(1).foreground().color().alpha() == 0


def test_rgb_color_with_default_alpha_is_previewed():
    entity = ChemicalEntity(
        name="water",
        molecular_weight=18.015,
        color_red=0,
        color_green=0,
        color_blue=200,
        color_alpha=0,
    )

    assert "rgba(0, 0, 200, 255)" in _swatch_stylesheet(entity)


def test_valid_add_registers_compound_and_refreshes_list(
    compound_list: CompoundList,
    monkeypatch,
):
    entity = ChemicalEntity(
        name="water",
        molecular_weight="18.015 g/mol",
        cp_liquid="75.3 J/(mol*K)",
        cp_gas="33.6 J/(mol*K)",
        density_liquid="997 kg/m^3",
        color_red=0x33,
        color_green=0x66,
        color_blue=0xFF,
        color_alpha=255,
    )
    _patch_dialog(monkeypatch, entity=entity)

    compound_list._open_add_dialog()

    registered = COMPOUNDS["water"]
    assert _magnitude(registered.molecular_weight, "g/mol") == pytest.approx(18.015)
    assert _magnitude(registered.cp_liquid, "J/(mol*K)") == pytest.approx(75.3)
    assert _magnitude(registered.cp_gas, "J/(mol*K)") == pytest.approx(33.6)
    assert _magnitude(registered.density_liquid, "kg/m^3") == pytest.approx(997)
    assert registered.rgb_hex == "#3366FF"
    assert registered.color_alpha == 255
    assert compound_list.visible_names() == ["air", "water"]
    assert compound_list.selected_name() == "water"


def test_cancelled_add_does_not_mutate_compounds(
    compound_list: CompoundList,
    monkeypatch,
):
    _patch_dialog(monkeypatch, accepted=False, entity=None)

    compound_list._open_add_dialog()

    assert COMPOUNDS.names == ["air"]
    assert compound_list.visible_names() == ["air"]


def test_invalid_name_is_rejected(compound_list: CompoundList, monkeypatch):
    _patch_dialog(
        monkeypatch,
        entity=ChemicalEntity(name="bad name", molecular_weight=18.015),
    )

    compound_list._open_add_dialog()

    assert COMPOUNDS.names == ["air"]
    assert compound_list.visible_names() == ["air"]


def test_duplicate_name_is_rejected(compound_list: CompoundList, monkeypatch):
    COMPOUNDS.register(ChemicalEntity(name="water", molecular_weight=18.015))
    compound_list.sync()
    _patch_dialog(
        monkeypatch,
        entity=ChemicalEntity(name="water", molecular_weight=20),
    )

    compound_list._open_add_dialog()

    assert _magnitude(COMPOUNDS["water"].molecular_weight, "g/mol") == pytest.approx(
        18.015
    )
    assert compound_list.visible_names() == ["air", "water"]


def test_remove_user_added_compound_updates_registry_and_list(
    compound_list: CompoundList,
    qtbot: QtBot,
):
    COMPOUNDS.register(ChemicalEntity(name="water", molecular_weight=18.015))
    compound_list.sync()
    compound_list.list_widget.setCurrentRow(1)

    qtbot.mouseClick(compound_list.remove_button, Qt.LeftButton)

    assert COMPOUNDS.names == ["air"]
    assert compound_list.visible_names() == ["air"]


def test_remove_air_is_blocked(compound_list: CompoundList):
    compound_list.list_widget.setCurrentRow(0)

    compound_list.remove_selected_compound()

    assert COMPOUNDS.names == ["air"]
    assert compound_list.visible_names() == ["air"]
    assert not compound_list.remove_button.isEnabled()


def test_compound_dialog_defaults_show_expected_quantity_units(qtbot: QtBot):
    dialog = CompoundDialog()
    qtbot.addWidget(dialog)

    cards = dialog.editor_widget._cards
    assert cards["molecular_weight"]._unit_combo.currentText() == "g/mol"
    assert cards["cp_gas"]._unit_combo.currentText() == "J/(mol*K)"
    assert cards["density_liquid"]._unit_combo.currentText() == "kg/m^3"


def test_setup_window_exposes_compounds_page(qtbot: QtBot):
    window = SetupWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)

    assert isinstance(window.compounds_widget, CompoundsWidget)
    assert window.compound_list is window.compounds_widget
    assert hasattr(window.compounds_widget, "edit_inventory_button")
    assert not hasattr(window.compounds_widget, "inventory_status")
    assert window.stackWidget.indexOf(window.compound_list) >= 0
    assert (
        window.navigationInterface.widget(window.compound_list.objectName()) is not None
    )


def test_inventory_status_lists_inventory_components_and_registered_compounds(
    qtbot: QtBot,
):
    COMPOUNDS.register(ChemicalEntity(name="water", molecular_weight=18.015))
    bottle = create_component(
        figure="GlassBottle",
        name="BottleA",
        position=(0.0, 0.0),
    )
    pump = create_component(
        figure="HPLCPump",
        name="PumpA",
        position=(0.0, 0.0),
    )
    widget = InventoryStatusWidget(
        component_provider=lambda: [("BottleA", bottle), ("PumpA", pump)]
    )
    qtbot.addWidget(widget)
    widget.show()
    qtbot.waitExposed(widget)

    assert widget.visible_inventory_names() == ["BottleA / Inventory"]
    assert "air" in widget.species_names()
    assert "water" in widget.species_names()
    assert widget.capacity_label.text() == "Capacity: 1 ml"


def test_inventory_status_dialog_cancel_preserves_inventory(qtbot: QtBot):
    COMPOUNDS.register(ChemicalEntity(name="water", molecular_weight=18.015))
    bottle = create_component(
        figure="GlassBottle",
        name="BottleA",
        position=(0.0, 0.0),
    )
    dialog = InventoryStatusDialog(component_provider=lambda: [("BottleA", bottle)])
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)

    widget = dialog.inventory_widget
    widget.volume_spin.setValue(2.5)
    widget._amount_spins["water"].setValue(0.125)
    dialog.reject()

    inventory = bottle.inf.internal_inventory
    assert inventory is not None
    assert inventory.liq_content.volume == 0
    assert inventory.liq_content.initial_species == {}


def test_inventory_status_dialog_save_applies_mol_phase_content(qtbot: QtBot):
    COMPOUNDS.register(ChemicalEntity(name="water", molecular_weight=18.015))
    bottle = create_component(
        figure="GlassBottle",
        name="BottleA",
        position=(0.0, 0.0),
        capacity="10 ml",
    )
    dialog = InventoryStatusDialog(component_provider=lambda: [("BottleA", bottle)])
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)

    widget = dialog.inventory_widget
    widget.volume_spin.setValue(2.5)
    widget._amount_spins["water"].setValue(0.125)
    widget.phase_combo.setCurrentIndex(1)
    widget.volume_spin.setValue(7.5)
    dialog._save()

    inventory = bottle.inf.internal_inventory
    assert inventory is not None
    assert inventory.liq_content.volume == pytest.approx(2.5e-6)
    assert inventory.liq_content.initial_species == {"water": 0.125}


def test_inventory_status_dialog_converts_ml_amount_to_moles(qtbot: QtBot):
    COMPOUNDS.register(
        ChemicalEntity(
            name="water",
            molecular_weight=18.015,
            density_liquid=997.0,
        )
    )
    bottle = create_component(
        figure="GlassBottle",
        name="BottleA",
        position=(0.0, 0.0),
        capacity="10 ml",
    )
    dialog = InventoryStatusDialog(component_provider=lambda: [("BottleA", bottle)])
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)

    widget = dialog.inventory_widget
    widget.amount_unit_combo.setCurrentIndex(1)
    widget.volume_spin.setValue(2.5)
    widget._amount_spins["water"].setValue(1.0)
    widget.phase_combo.setCurrentIndex(1)
    widget.volume_spin.setValue(7.5)
    dialog._save()

    inventory = bottle.inf.internal_inventory
    assert inventory is not None
    expected_moles = 1e-6 / COMPOUNDS["water"].molar_volume_liquid()
    assert inventory.liq_content.initial_species == {
        "water": pytest.approx(expected_moles)
    }


def test_inventory_status_amount_unit_switch_preserves_amount(qtbot: QtBot):
    COMPOUNDS.register(
        ChemicalEntity(
            name="water",
            molecular_weight=18.015,
            density_liquid=997.0,
        )
    )
    bottle = create_component(
        figure="GlassBottle",
        name="BottleA",
        position=(0.0, 0.0),
        capacity="10 ml",
    )
    dialog = InventoryStatusDialog(component_provider=lambda: [("BottleA", bottle)])
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)

    widget = dialog.inventory_widget
    widget._amount_spins["water"].setValue(0.01)
    widget.amount_unit_combo.setCurrentIndex(1)
    ml_amount = widget._amount_spins["water"].value()
    widget.amount_unit_combo.setCurrentIndex(0)

    assert ml_amount == pytest.approx(
        0.01 * COMPOUNDS["water"].molar_volume_liquid() * 1e6
    )
    assert widget._amount_spins["water"].value() == pytest.approx(0.01)


def test_inventory_status_context_changes_do_not_duplicate_species_rows(
    qtbot: QtBot,
):
    COMPOUNDS.register(
        ChemicalEntity(
            name="water",
            molecular_weight=18.015,
            density_liquid=997.0,
        )
    )
    bottle = create_component(
        figure="GlassBottle",
        name="BottleA",
        position=(0.0, 0.0),
        capacity="10 ml",
    )
    dialog = InventoryStatusDialog(component_provider=lambda: [("BottleA", bottle)])
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)

    widget = dialog.inventory_widget
    initial_count = widget.species_layout.count()
    widget.phase_combo.setCurrentIndex(1)
    widget.amount_unit_combo.setCurrentIndex(1)
    widget.amount_unit_combo.setCurrentIndex(0)

    assert widget.species_layout.count() == initial_count


def test_inventory_status_capacity_text_is_compact():
    assert (
        InventoryStatusWidget._capacity_text(SimpleNamespace(capacity_value=10e-6))
        == "Capacity: 10 ml"
    )
    assert (
        InventoryStatusWidget._capacity_text(SimpleNamespace(capacity_value=1e-3))
        == "Capacity: 1 L"
    )
    assert (
        InventoryStatusWidget._capacity_text(SimpleNamespace(capacity_value=1e7))
        == "Capacity: not limited"
    )
    assert (
        InventoryStatusWidget._capacity_text(SimpleNamespace(capacity_value=0.0)) == ""
    )


def test_inventory_status_dialog_rejects_volume_over_capacity(qtbot: QtBot):
    COMPOUNDS.register(ChemicalEntity(name="water", molecular_weight=18.015))
    bottle = create_component(
        figure="GlassBottle",
        name="BottleA",
        position=(0.0, 0.0),
    )
    dialog = InventoryStatusDialog(component_provider=lambda: [("BottleA", bottle)])
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)

    widget = dialog.inventory_widget
    widget.volume_spin.setValue(2.0)
    widget._amount_spins["water"].setValue(0.125)
    dialog._save()

    inventory = bottle.inf.internal_inventory
    assert inventory is not None
    assert inventory.liq_content.volume == 0
    assert inventory.liq_content.initial_species == {}
