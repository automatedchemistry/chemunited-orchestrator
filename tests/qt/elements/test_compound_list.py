from __future__ import annotations

import pytest
from chemunited_core.compounds import COMPOUNDS, ChemicalEntity
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFrame
from pytestqt.qtbot import QtBot

from chemunited.qt.elements.compounds import CompoundDialog, CompoundList
from chemunited.qt.elements.compounds.compound_list import _swatch_stylesheet
from chemunited.qt.setup import SetupWindow


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
        "chemunited.qt.elements.compounds.compound_list.CompoundDialog",
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

    assert window.stackWidget.indexOf(window.compound_list) >= 0
    assert (
        window.navigationInterface.widget(window.compound_list.objectName()) is not None
    )
