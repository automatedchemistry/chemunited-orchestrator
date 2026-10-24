"""Unit tests for the live view's device pictures (api/command_tracker.py)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from loguru import logger

from chemunited_workflow.api.command_tracker import INSTALL_HINT, load_command_tracker
from chemunited_workflow.api.device_state import DeviceStateStore, UnknownPicture
from chemunited_workflow.command_events import CommandEvent

EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "custom_project"


@pytest.fixture
def messages():
    captured: list[str] = []
    sink_id = logger.add(lambda message: captured.append(str(message)), level="INFO")
    yield captured
    logger.remove(sink_id)


def _project(tmp_path: Path, build_draw_body: str) -> Path:
    (tmp_path / "draw").mkdir()
    (tmp_path / "draw" / "setup.py").write_text(
        "def build_draw(platform):\n" + build_draw_body, encoding="utf-8"
    )
    return tmp_path


def test_the_example_project_pictures_its_valves_badges_and_relay():
    tracker = load_command_tracker(EXAMPLE)

    assert tracker is not None
    assert {
        name: tracker.kind(name)
        for name in (
            "AS injection",
            "Reagent Valve",
            "S valve",
            "S2way",
            "flowmeter",
            "Relay",
            "HPLCpump",
            "Waste",
        )
    } == {
        "AS injection": "rotor",
        "Reagent Valve": "rotor",
        "S valve": "solenoid",
        "S2way": "two-way",
        "flowmeter": "mfc",
        "Relay": "relay",
        "HPLCpump": None,
        "Waste": None,
    }


def test_derive_follows_the_commands_a_device_gets():
    tracker = load_command_tracker(EXAMPLE)
    assert tracker is not None

    assert tracker.derive("AS injection", "position", {"connect": "[[2, 3]]"}) == {
        "links": [[1, 6], [2, 3], [4, 5]]
    }
    assert tracker.derive("S valve", "close", None) == {"open": False}
    with pytest.raises(UnknownPicture, match="doesn't say"):
        tracker.derive("AS injection", "home", {})
    with pytest.raises(UnknownPicture, match="no picture"):
        tracker.derive("HPLCpump", "infuse", {})


def test_the_store_draws_pictures_with_the_tracker():
    store = DeviceStateStore(["Reagent Valve"], deriver=load_command_tracker(EXAMPLE))

    store.observer("run-1")(
        CommandEvent(
            kind="started",
            component="Reagent Valve",
            command="position",
            params={"connect": "[[0, 4]]"},
            call_id=1,
        )
    )

    state = store.snapshot()["devices"]["Reagent Valve"]
    assert (state["kind"], state["picture"]) == ("rotor", {"links": [[0, 4]]})


def test_only_pictured_components_are_built_and_other_calls_do_nothing(
    tmp_path, messages
):
    project = _project(
        tmp_path,
        "    platform.add_compound(name='water')\n"
        "    platform.add_component(name='V', figure='SixPortDistributionValve')\n"
        "    platform.add_component(name='W', figure='Sink', capacity='not a volume')\n"
        "    platform.add_component(name='X', figure='NotAFigure')\n"
        "    platform.add_component(name='R', figure='MultiChannelRelay', channels=99)\n"
        "    platform.add_connection(origin='V', destiny='W', origin_port=1, destiny_port=1)\n"
        "    platform.add_display(name='T', position=(0, 0), component='V', command='p', kwargs={})\n"
        "    platform.set_port_closed('V', 2)\n",
    )

    tracker = load_command_tracker(project)

    assert tracker is not None
    assert (tracker.kind("V"), tracker.kind("W"), tracker.kind("X")) == (
        "rotor",
        None,
        None,
    )
    assert tracker.kind("R") is None  # 99 channels is invalid: skipped, with a reason
    assert any("no picture for 'R'" in message for message in messages)


def test_a_broken_setup_py_turns_pictures_off(tmp_path, messages):
    project = _project(tmp_path, "    raise RuntimeError('half-edited')\n")

    assert load_command_tracker(project) is None
    assert any("half-edited" in message for message in messages)


def test_a_project_without_setup_py_has_no_pictures(tmp_path, messages):
    assert load_command_tracker(tmp_path) is None
    assert any("doesn't exist" in message for message in messages)


def test_without_chemunited_core_there_are_no_pictures(monkeypatch, messages):
    for name in list(sys.modules):
        if name == "chemunited_core" or name.startswith("chemunited_core."):
            monkeypatch.setitem(sys.modules, name, None)
    monkeypatch.setitem(sys.modules, "chemunited_core", None)

    assert load_command_tracker(EXAMPLE) is None
    assert any(INSTALL_HINT in message for message in messages)
