"""Tests for the LCD readouts of the dashboard's live platform view (desktop side).

What is tested:
- The variable picker lists a device's GET commands only, from its protocol
  definition, and marks the ones in the project's monitoring list.
- An LCD saves to draw/setup.py as ``platform.add_display(...)`` and loads back.
- The export leaves LCDs out of platform.svg and writes their box and binding
  to platform-live.json.
- Save warns about an LCD whose device or variable no longer exists.
- Adding from the Add panel, and deleting with the Delete key.
"""

from __future__ import annotations

import json

import pytest
from PyQt5.QtCore import Qt
from pytestqt.qtbot import QtBot

from chemunited.elements.display import (
    LcdDisplayDialog,
    LcdDisplayItem,
    device_variables,
)
from chemunited.elements.display.dialog import MONITORED_SUFFIX
from chemunited.project import storage
from chemunited.project.platform_svg import export_platform_svg
from chemunited.project.session import ProjectSession
from chemunited.setup import SetupWindow


@pytest.fixture
def window(qtbot: QtBot):
    w = SetupWindow()
    qtbot.addWidget(w)
    w.show()
    qtbot.waitExposed(w)
    return w


@pytest.fixture
def project(window: SetupWindow, tmp_path):
    working_dir = tmp_path / "demo"
    session = ProjectSession()
    session.new(name="demo", location=tmp_path)
    window.orchestrator.working_dir = working_dir
    window.orchestrator._session = session
    return working_dir


def _platform(window: SetupWindow) -> None:
    orchestrator = window.orchestrator
    orchestrator.add_component(name="P1", figure="PressureSensor", position=(0.0, 0.0))
    orchestrator.add_component(
        name="ADC", figure="MultiChannelADC", position=(400.0, 300.0)
    )
    orchestrator.add_display(
        name="Inlet pressure",
        position=(200.0, 150.0),
        component="P1",
        command="read-pressure",
    )
    orchestrator.add_display(
        name="Channel 2",
        position=(220.0, 220.0),
        component="ADC",
        command="read",
        kwargs={"channel": "2"},
    )


def test_the_variables_are_the_devices_get_commands():
    assert device_variables("MultiChannelADC", "adc") == {
        "read": {"channel": "1"},
        "read_all": {},
    }
    assert "set" not in device_variables("MultiChannelDAC", "dac")


def test_the_picker_marks_monitored_variables_and_offers_their_defaults(qtbot):
    dialog = LcdDisplayDialog(
        devices={"ADC": "MultiChannelADC", "P1": "PressureSensor"},
        monitored=[{"component": "ADC", "command": "read", "kwargs": {"channel": "1"}}],
        taken_names=set(),
        name="LCD 1",
        position=(0.0, 0.0),
        component="ADC",
    )
    qtbot.addWidget(dialog)

    items = [
        dialog.variable_combo.itemText(i) for i in range(dialog.variable_combo.count())
    ]
    assert items == ["read" + MONITORED_SUFFIX, "read_all"]
    assert json.loads(dialog.params_edit.text()) == {"channel": "1"}
    assert dialog.monitoring_hint.text() == "In the monitoring list."

    dialog.params_edit.setText('{"channel": "2"}')
    assert "not monitored" in dialog.monitoring_hint.text()


def test_the_dialog_refuses_a_taken_name_and_bad_parameters(qtbot):
    dialog = LcdDisplayDialog(
        devices={"ADC": "MultiChannelADC"},
        monitored=[],
        taken_names={"LCD 1"},
        name="LCD 1",
        position=(0.0, 0.0),
    )
    qtbot.addWidget(dialog)

    dialog._save()
    assert dialog.get_result_instance() is None
    assert "already called" in dialog.error_label.text()

    dialog.name_edit.setText("LCD 2")
    dialog.params_edit.setText("[1, 2]")
    dialog._save()
    assert dialog.get_result_instance() is None
    assert "JSON object" in dialog.error_label.text()

    dialog.params_edit.setText('{"channel": "3"}')
    dialog._save()
    result = dialog.get_result_instance()
    assert result is not None
    assert (result.name, result.component, result.command, result.kwargs) == (
        "LCD 2",
        "ADC",
        "read",
        {"channel": "3"},
    )


def test_an_lcd_saves_to_setup_py_and_loads_back(window, project, qtbot):
    _platform(window)

    window.orchestrator.save()

    setup = (project / "draw" / "setup.py").read_text(encoding="utf-8")
    assert "platform.add_display(" in setup
    displays = storage.load_draw(project)["displays"]
    assert displays == [
        {
            "name": "Inlet pressure",
            "position": (200.0, 150.0),
            "component": "P1",
            "command": "read-pressure",
            "kwargs": {},
        },
        {
            "name": "Channel 2",
            "position": (220.0, 220.0),
            "component": "ADC",
            "command": "read",
            "kwargs": {"channel": "2"},
        },
    ]

    other = SetupWindow()
    qtbot.addWidget(other)
    other.orchestrator.load_draw_data(storage.load_draw(project))
    restored = other.orchestrator.displays["Channel 2"]
    assert restored.display.kwargs == {"channel": "2"}
    assert (restored.pos().x(), restored.pos().y()) == (220.0, 220.0)
    assert restored.scene() is other.scene_attribute


def test_the_export_leaves_lcds_out_and_maps_them(window, project, tmp_path):
    _platform(window)
    window.orchestrator.save()
    live = json.loads((project / "draw" / "platform-live.json").read_text("utf-8"))

    assert live["displays"]["Channel 2"]["component"] == "ADC"
    assert live["displays"]["Channel 2"]["command"] == "read"
    assert live["displays"]["Channel 2"]["kwargs"] == {"channel": "2"}
    x, y, w, h = live["displays"]["Inlet pressure"]["box"]
    assert w > 0 and h > 0

    # The LCDs lie inside the drawing, so without them the SVG is the same.
    for item in list(window.orchestrator.displays.values()):
        assert item.isVisible()
        window.orchestrator.remove_display(item.name)
    bare = tmp_path / "bare.svg"
    export_platform_svg(
        window.scene_attribute, bare, components=window.orchestrator.components.items()
    )
    assert bare.read_bytes() == (project / "draw" / "platform.svg").read_bytes()


def test_save_warns_about_an_lcd_whose_device_is_gone(window, project):
    _platform(window)
    window.orchestrator.remove_component("P1")

    assert window.orchestrator.stale_display_bindings() == [
        "LCD 'Inlet pressure' shows device 'P1', which no longer exists."
    ]


def test_save_warns_about_an_lcd_whose_variable_is_gone(window, project):
    window.orchestrator.add_component(
        name="P1", figure="PressureSensor", position=(0, 0)
    )
    window.orchestrator.add_display(
        name="Old", position=(0, 100), component="P1", command="read-flow"
    )

    assert window.orchestrator.stale_display_bindings() == [
        "LCD 'Old' shows 'read-flow', which 'P1' doesn't have."
    ]


def test_adding_from_the_add_panel_opens_the_dialog(window, monkeypatch):
    window.orchestrator.add_component(
        name="P1", figure="PressureSensor", position=(0, 0)
    )

    def accept(dialog):
        dialog._save()
        return dialog.get_result_instance() is not None

    monkeypatch.setattr(LcdDisplayDialog, "exec", accept)
    window.orchestrator.request_add_display((50.0, 60.0))

    item = window.orchestrator.displays["LCD 1"]
    assert isinstance(item, LcdDisplayItem)
    assert (item.display.component, item.display.command) == ("P1", "read-pressure")
    assert (item.pos().x(), item.pos().y()) == (50.0, 60.0)


def test_an_lcd_needs_a_device_to_show(window, monkeypatch):
    opened = []
    monkeypatch.setattr(LcdDisplayDialog, "exec", lambda dialog: opened.append(1))

    window.orchestrator.request_add_display((0.0, 0.0))

    assert opened == [] and window.orchestrator.displays == {}


def test_the_delete_key_removes_a_selected_lcd(window, qtbot):
    _platform(window)
    item = window.orchestrator.displays["Inlet pressure"]
    item.setSelected(True)

    qtbot.keyClick(window.drawGraph, Qt.Key_Delete)
    qtbot.waitUntil(lambda: "Inlet pressure" not in window.orchestrator.displays)

    assert item.scene() is None
    assert "Channel 2" in window.orchestrator.displays
