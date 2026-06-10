from __future__ import annotations

import pytest
from chemunited_core.compounds import COMPOUNDS, ChemicalEntity
from PyQt5.QtCore import Qt
from pytestqt.qtbot import QtBot

from chemunited.qt.elements.compounds import CompoundList
from chemunited.qt.setup import SetupWindow


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


def _fill_required_form(
    widget: CompoundList,
    *,
    name: str = "water",
    molecular_weight: str = "18.015",
) -> None:
    widget.name_edit.setText(name)
    widget.molecular_weight_edit.setText(molecular_weight)


def test_initial_list_contains_registered_compounds(compound_list: CompoundList):
    assert compound_list.visible_names() == ["air"]


def test_valid_add_registers_compound_and_refreshes_list(
    compound_list: CompoundList,
    qtbot: QtBot,
):
    _fill_required_form(compound_list, name="water", molecular_weight="18.015")
    compound_list.cp_liquid_edit.setText("75.3")
    compound_list.cp_gas_edit.setText("33.6")
    compound_list.density_liquid_edit.setText("997")
    compound_list.color_edit.setText("#3366FF")

    qtbot.mouseClick(compound_list.add_button, Qt.LeftButton)

    entity = COMPOUNDS["water"]
    assert isinstance(entity, ChemicalEntity)
    assert entity.molecular_weight == pytest.approx(18.015)
    assert entity.cp_liquid == pytest.approx(75.3)
    assert entity.cp_gas == pytest.approx(33.6)
    assert entity.density_liquid == pytest.approx(997)
    assert entity.color == "#3366FF"
    assert compound_list.visible_names() == ["air", "water"]
    assert compound_list.name_edit.text() == ""


@pytest.mark.parametrize(
    ("name", "molecular_weight"),
    [
        ("", "18.015"),
        ("bad name", "18.015"),
        ("water", ""),
        ("water", "not-a-number"),
        ("water", "0"),
    ],
)
def test_invalid_required_fields_do_not_mutate_compounds(
    compound_list: CompoundList,
    qtbot: QtBot,
    name: str,
    molecular_weight: str,
):
    _fill_required_form(
        compound_list,
        name=name,
        molecular_weight=molecular_weight,
    )

    qtbot.mouseClick(compound_list.add_button, Qt.LeftButton)

    assert COMPOUNDS.names == ["air"]
    assert compound_list.visible_names() == ["air"]


def test_invalid_optional_float_does_not_mutate_compounds(
    compound_list: CompoundList,
    qtbot: QtBot,
):
    _fill_required_form(compound_list)
    compound_list.cp_liquid_edit.setText("not-a-number")

    qtbot.mouseClick(compound_list.add_button, Qt.LeftButton)

    assert COMPOUNDS.names == ["air"]
    assert compound_list.visible_names() == ["air"]


def test_duplicate_name_is_rejected(compound_list: CompoundList, qtbot: QtBot):
    COMPOUNDS.register(ChemicalEntity(name="water", molecular_weight=18.015))
    compound_list.sync()
    _fill_required_form(compound_list, name="water", molecular_weight="20")

    qtbot.mouseClick(compound_list.add_button, Qt.LeftButton)

    assert COMPOUNDS["water"].molecular_weight == pytest.approx(18.015)
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


def test_setup_window_exposes_compounds_page(qtbot: QtBot):
    window = SetupWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)

    assert window.stackWidget.indexOf(window.compound_list) >= 0
    assert (
        window.navigationInterface.widget(window.compound_list.objectName()) is not None
    )
