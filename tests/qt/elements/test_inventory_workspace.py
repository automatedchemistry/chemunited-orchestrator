from __future__ import annotations

from types import SimpleNamespace

import pytest
from chemunited_core.compounds import COMPOUNDS, ChemicalEntity
from PyQt5.QtCore import QItemSelectionModel
from PyQt5.QtWidgets import QWidget
from pytestqt.qtbot import QtBot
from qfluentwidgets import ToolButton

from chemunited.elements.component import create_component
from chemunited.elements.compounds import CompoundList
from chemunited.elements.inventory import InventoryWorkspace, inventory_capacity_m3
from chemunited.orchestrator.inventory_state import inventory_uses_compound


@pytest.fixture(autouse=True)
def reset_compounds():
    COMPOUNDS.clear()
    yield
    COMPOUNDS.clear()


def _water() -> ChemicalEntity:
    return ChemicalEntity(
        name="water",
        molecular_weight=18.015,
        density_liquid=997.0,
    )


def _workspace(qtbot: QtBot, *components) -> InventoryWorkspace:
    widget = InventoryWorkspace(
        component_provider=lambda: [
            (component.inf.name, component) for component in components
        ]
    )
    qtbot.addWidget(widget)
    widget.show()
    qtbot.waitExposed(widget)
    widget._show_success = lambda *_args: None
    return widget


def _select_rows(widget: InventoryWorkspace, *rows: int) -> None:
    selection_model = widget.table.selectionModel()
    assert selection_model is not None
    widget.table.clearSelection()
    for row in rows:
        selection_model.select(
            widget.table.model().index(row, 0),
            QItemSelectionModel.Select | QItemSelectionModel.Rows,
        )


def test_workspace_lists_only_inventory_components_and_filters(qtbot: QtBot):
    COMPOUNDS.register(_water())
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
    widget = _workspace(qtbot, bottle, pump)

    assert widget.visible_inventory_names() == ["BottleA / Inventory"]
    assert widget.table.item(0, 6).text() == "Air only"
    assert "air" in widget.table.item(0, 5).text()

    widget.search.setText("missing")
    assert widget.visible_inventory_names() == []
    widget.search.setText("air")
    assert widget.visible_inventory_names() == ["BottleA / Inventory"]


def test_capacity_resolver_supports_vessels_syringes_and_unlimited_values():
    bottle = create_component(
        figure="GlassBottle",
        name="BottleA",
        position=(0.0, 0.0),
        capacity="25 ml",
    )
    syringe = create_component(
        figure="SyringePump",
        name="SyringeA",
        position=(0.0, 0.0),
    )

    assert inventory_capacity_m3(bottle.inf) == pytest.approx(25e-6)
    assert inventory_capacity_m3(syringe.inf) == pytest.approx(10e-6)
    assert inventory_capacity_m3(SimpleNamespace(capacity_value=1e7)) is None
    assert inventory_capacity_m3(SimpleNamespace()) is None


def test_auto_headspace_updates_gas_volume_and_air_amount(qtbot: QtBot):
    bottle = create_component(
        figure="GlassBottle",
        name="BottleA",
        position=(0.0, 0.0),
        capacity="10 ml",
    )
    widget = _workspace(qtbot, bottle)

    assert widget.auto_headspace_switch.isChecked()
    assert widget.gas_editor.volume_spin.isReadOnly()

    widget.liquid_editor.volume_spin.setValue(4.0)

    entry = widget._active_entry()
    assert entry is not None
    gas = entry.draft_inventory.gas_content
    assert gas.volume == pytest.approx(6e-6)
    expected_air = (
        6e-6
        / COMPOUNDS["air"]
        .molar_volume_gas(
            gas.initial_temperature,
            gas.initial_pressure,
        )
        .magnitude
    )
    assert gas.initial_species == {"air": pytest.approx(expected_air)}
    assert widget.gas_editor.volume_spin.value() == pytest.approx(6.0)
    assert widget.apply_button.isEnabled()


def test_unlocked_phase_volumes_show_overfill_and_block_apply(qtbot: QtBot):
    bottle = create_component(
        figure="GlassBottle",
        name="BottleA",
        position=(0.0, 0.0),
        capacity="10 ml",
    )
    widget = _workspace(qtbot, bottle)
    errors: list[tuple[str, str]] = []
    widget._show_error = lambda title, content: errors.append((title, content))

    widget.auto_headspace_switch.setChecked(False)
    widget.liquid_editor.volume_spin.setValue(7.0)
    widget.gas_editor.volume_spin.setValue(5.0)

    assert widget.table.item(0, 6).text() == "Over capacity"
    assert not widget.apply_button.isEnabled()
    assert widget.apply_changes() is False
    assert errors and "12 mL of 10 mL" in errors[0][1]
    assert bottle.inf.internal_inventory.liq_content.volume == 0.0


def test_concentration_is_a_view_of_preserved_moles(qtbot: QtBot):
    COMPOUNDS.register(_water())
    bottle = create_component(
        figure="GlassBottle",
        name="BottleA",
        position=(0.0, 0.0),
        capacity="10 ml",
    )
    widget = _workspace(qtbot, bottle)
    widget.liquid_editor.volume_spin.setValue(2.0)
    combo = widget.liquid_editor.add_combo
    combo.setCurrentIndex(combo.findData("water"))
    widget.liquid_editor.add_button.click()
    row = widget.liquid_editor._rows["water"]
    row.unit_combo.setCurrentIndex(row.unit_combo.findData("mol/L"))
    row.amount_spin.setValue(0.5)

    assert row.moles() == pytest.approx(0.001)

    widget.liquid_editor.volume_spin.setValue(4.0)

    assert row.moles() == pytest.approx(0.001)
    assert row.amount_spin.value() == pytest.approx(0.25)
    assert widget.apply_changes()
    assert bottle.inf.internal_inventory.liq_content.initial_species == {
        "water": pytest.approx(0.001)
    }


def test_equivalent_volume_unit_uses_compound_molar_volume(qtbot: QtBot):
    COMPOUNDS.register(_water())
    bottle = create_component(
        figure="GlassBottle",
        name="BottleA",
        position=(0.0, 0.0),
        capacity="10 ml",
    )
    widget = _workspace(qtbot, bottle)
    combo = widget.liquid_editor.add_combo
    combo.setCurrentIndex(combo.findData("water"))
    widget.liquid_editor.add_button.click()
    row = widget.liquid_editor._rows["water"]

    unit_index = row.unit_combo.findData("equiv. mL")
    assert unit_index >= 0
    row.unit_combo.setCurrentIndex(unit_index)
    row.amount_spin.setValue(1.0)

    expected = 1e-6 / COMPOUNDS["water"].molar_volume_liquid().magnitude
    assert row.moles() == pytest.approx(expected)


def test_compound_remove_button_is_a_centered_icon_control(qtbot: QtBot):
    COMPOUNDS.register(_water())
    bottle = create_component(
        figure="GlassBottle",
        name="BottleA",
        position=(0.0, 0.0),
    )
    widget = _workspace(qtbot, bottle)
    combo = widget.liquid_editor.add_combo
    combo.setCurrentIndex(combo.findData("water"))
    widget.liquid_editor.add_button.click()

    button = widget.liquid_editor._rows["water"].remove_button

    assert isinstance(button, ToolButton)
    assert button.width() == button.height() == 34
    assert button.iconSize().width() == button.iconSize().height() == 16


def test_apply_and_discard_preserve_staged_editing(qtbot: QtBot):
    bottle = create_component(
        figure="GlassBottle",
        name="BottleA",
        position=(0.0, 0.0),
        capacity="10 ml",
    )
    widget = _workspace(qtbot, bottle)

    widget.liquid_editor.volume_spin.setValue(3.0)
    assert widget.is_dirty
    assert bottle.inf.internal_inventory.liq_content.volume == 0.0

    widget.discard_changes()
    assert not widget.is_dirty
    assert widget.liquid_editor.volume_spin.value() == 0.0

    widget.liquid_editor.volume_spin.setValue(3.0)
    assert widget.apply_changes()
    assert not widget.is_dirty
    assert bottle.inf.internal_inventory.liq_content.volume == pytest.approx(3e-6)


def test_non_forced_sync_preserves_drafts_across_component_rename(qtbot: QtBot):
    bottle = create_component(
        figure="GlassBottle",
        name="BottleA",
        position=(0.0, 0.0),
        capacity="10 ml",
    )
    names = {id(bottle): "BottleA"}
    widget = InventoryWorkspace(
        component_provider=lambda: [(names[id(bottle)], bottle)]
    )
    qtbot.addWidget(widget)
    widget.show()
    qtbot.waitExposed(widget)
    widget.liquid_editor.volume_spin.setValue(2.0)

    names[id(bottle)] = "RenamedBottle"
    widget.sync(force=False)

    assert widget.visible_inventory_names() == ["RenamedBottle / Inventory"]
    assert widget.liquid_editor.volume_spin.value() == pytest.approx(2.0)
    assert widget.is_dirty


def test_bulk_apply_copies_both_phases_to_selected_wells(qtbot: QtBot):
    tray = create_component(
        figure="Vial",
        name="TrayA",
        position=(0.0, 0.0),
        row=2,
        column=2,
        capacity="1 ml",
    )
    widget = _workspace(qtbot, tray)
    assert widget.table.rowCount() == 4

    _select_rows(widget, 0, 1, 2)
    widget.table.setCurrentCell(0, 0)
    widget.liquid_editor.volume_spin.setValue(0.25)
    _select_rows(widget, 0, 1, 2)
    widget._apply_active_to_selection()

    for entry in widget._entries[:3]:
        assert entry.draft_inventory.liq_content.volume == pytest.approx(0.25e-6)
        assert entry.draft_inventory.gas_content.volume == pytest.approx(0.75e-6)
    assert widget._entries[3].draft_inventory.liq_content.volume == 0.0
    assert widget.is_dirty


def test_bulk_apply_preflights_smaller_target_capacity(qtbot: QtBot):
    large = create_component(
        figure="GlassBottle",
        name="Large",
        position=(0.0, 0.0),
        capacity="10 ml",
    )
    small = create_component(
        figure="GlassBottle",
        name="Small",
        position=(0.0, 0.0),
        capacity="1 ml",
    )
    widget = _workspace(qtbot, large, small)
    errors: list[tuple[str, str]] = []
    widget._show_error = lambda title, content: errors.append((title, content))
    widget.liquid_editor.volume_spin.setValue(5.0)
    _select_rows(widget, 0, 1)

    widget._apply_active_to_selection()

    assert errors and "Small / Inventory" in errors[0][1]
    assert widget._entries[1].draft_inventory.liq_content.volume == 0.0


def test_bulk_apply_balances_headspace_for_each_target_capacity(qtbot: QtBot):
    small = create_component(
        figure="GlassBottle",
        name="Small",
        position=(0.0, 0.0),
        capacity="1 ml",
    )
    large = create_component(
        figure="GlassBottle",
        name="Large",
        position=(0.0, 0.0),
        capacity="10 ml",
    )
    widget = _workspace(qtbot, small, large)
    widget.liquid_editor.volume_spin.setValue(0.25)
    _select_rows(widget, 0, 1)

    widget._apply_active_to_selection()

    target = widget._entries[1].draft_inventory
    assert target.liq_content.volume == pytest.approx(0.25e-6)
    assert target.gas_content.volume == pytest.approx(9.75e-6)


def test_inventory_use_lookup_checks_both_phases():
    COMPOUNDS.register(_water())
    bottle = create_component(
        figure="GlassBottle",
        name="BottleA",
        position=(0.0, 0.0),
    )
    inventory = bottle.inf.internal_inventory
    inventory.liq_content.initial_species = {"water": 0.1}

    assert inventory_uses_compound([bottle], "water")
    assert not inventory_uses_compound([bottle], "missing")


def test_compound_removal_is_blocked_while_used_by_inventory(qtbot: QtBot):
    COMPOUNDS.register(_water())
    bottle = create_component(
        figure="GlassBottle",
        name="BottleA",
        position=(0.0, 0.0),
    )
    bottle.inf.internal_inventory.liq_content.initial_species = {"water": 0.1}
    host = QWidget()
    host.orchestrator = SimpleNamespace(
        components={"BottleA": bottle},
        reaction_uses_compound=lambda _name: False,
    )
    qtbot.addWidget(host)
    compound_list = CompoundList(host)
    compound_list.sync()
    compound_list.list_widget.setCurrentRow(1)
    warnings: list[str] = []
    compound_list._show_warning = warnings.append

    compound_list.remove_selected_compound()

    assert "water" in COMPOUNDS
    assert warnings and "initial inventory" in warnings[0]


def test_compound_removal_is_blocked_while_used_by_inventory_draft(qtbot: QtBot):
    COMPOUNDS.register(_water())
    bottle = create_component(
        figure="GlassBottle",
        name="BottleA",
        position=(0.0, 0.0),
    )
    workspace = _workspace(qtbot, bottle)
    combo = workspace.liquid_editor.add_combo
    combo.setCurrentIndex(combo.findData("water"))
    workspace.liquid_editor.add_button.click()
    workspace.liquid_editor._rows["water"].amount_spin.setValue(0.1)

    host = QWidget()
    host.orchestrator = SimpleNamespace(
        components={"BottleA": bottle},
        reaction_uses_compound=lambda _name: False,
    )
    host.inventory_widget = workspace
    qtbot.addWidget(host)
    compound_list = CompoundList(host)
    compound_list.sync()
    compound_list.list_widget.setCurrentRow(1)
    warnings: list[str] = []
    compound_list._show_warning = warnings.append

    compound_list.remove_selected_compound()

    assert "water" in COMPOUNDS
    assert warnings and "initial inventory" in warnings[0]
