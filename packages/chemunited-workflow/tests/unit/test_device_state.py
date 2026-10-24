"""Unit tests for the live platform view's device state store."""

from __future__ import annotations

from datetime import datetime

import pytest

from chemunited_workflow.api.device_state import DeviceStateStore, UnknownPicture
from chemunited_workflow.command_events import CommandEvent


def _event(kind, call_id=1, component="valve", command="position", **kwargs):
    return CommandEvent(
        kind=kind, component=component, command=command, call_id=call_id, **kwargs
    )


class _Deriver:
    """Pictures a valve's position; anything else it can't tell."""

    def kind(self, component):
        return "rotor" if component == "valve" else None

    def derive(self, component, command, params):
        if command != "position":
            raise UnknownPicture(f"'{command}' doesn't say where the rotor is.")
        if params["connect"] == "boom":
            raise RuntimeError("deriver bug")
        return {"links": [[0, int(params["connect"])]]}


def test_every_device_starts_unknown():
    store = DeviceStateStore(["valve", "pump"])

    snapshot = store.snapshot()

    assert snapshot["seq"] == 0
    assert snapshot["pictures"] is False
    assert snapshot["displays"] == {}
    assert snapshot["devices"]["pump"] == {
        "kind": None,
        "status": "unknown",
        "command": None,
        "picture": None,
        "error": None,
    }
    assert snapshot["devices"]["valve"]["status"] == "unknown"


def test_started_marks_the_device_running_with_its_command():
    store = DeviceStateStore(["valve"])

    store.observer("run-1")(
        _event("started", command="/position", params={"connect": "3"}, node="n1")
    )

    state = store.snapshot()["devices"]["valve"]
    assert state["status"] == "running"
    command = state["command"]
    assert (command["name"], command["params"]) == ("position", {"connect": "3"})
    assert (command["run"], command["node"]) == ("run-1", "n1")
    datetime.fromisoformat(command["at"])


def test_finished_marks_it_done():
    store = DeviceStateStore(["valve"])
    observer = store.observer()

    observer(_event("started"))
    observer(_event("finished"))

    state = store.snapshot()["devices"]["valve"]
    assert state["status"] == "done"
    assert state["command"]["run"] is None  # a manual command, not a run's


def test_failed_marks_it_failed_and_forgets_the_picture():
    store = DeviceStateStore(["valve"], deriver=_Deriver())
    observer = store.observer()

    observer(_event("started", params={"connect": "3"}))
    observer(_event("failed", error="Device did not report idle within 10s"))

    state = store.snapshot()["devices"]["valve"]
    assert state["status"] == "failed"
    assert state["picture"] is None
    assert state["error"] == "Device did not report idle within 10s"


def test_a_newer_command_takes_over_from_one_still_waiting():
    store = DeviceStateStore(["valve"])
    observer = store.observer()

    observer(_event("started", call_id=1, command="infuse"))
    observer(_event("started", call_id=2, command="stop"))
    observer(_event("finished", call_id=1, command="infuse"))
    assert store.snapshot()["devices"]["valve"]["status"] == "running"

    observer(_event("finished", call_id=2, command="stop"))
    state = store.snapshot()["devices"]["valve"]
    assert (state["status"], state["command"]["name"]) == ("done", "stop")


def test_the_deriver_draws_the_picture_when_the_command_starts():
    store = DeviceStateStore(["valve", "pump"], deriver=_Deriver())
    observer = store.observer()

    observer(_event("started", params={"connect": "3"}))

    snapshot = store.snapshot()
    assert snapshot["pictures"] is True
    assert snapshot["devices"]["valve"]["kind"] == "rotor"
    assert snapshot["devices"]["valve"]["picture"] == {"links": [[0, 3]]}
    assert snapshot["devices"]["pump"]["kind"] is None


def test_an_unrecognised_command_makes_the_state_unknown_with_the_reason():
    store = DeviceStateStore(["valve"], deriver=_Deriver())
    observer = store.observer()
    observer(_event("started", call_id=1, params={"connect": "3"}))
    observer(_event("finished", call_id=1))

    observer(_event("started", call_id=2, command="home"))
    assert store.snapshot()["devices"]["valve"]["status"] == "running"
    observer(_event("finished", call_id=2, command="home"))

    state = store.snapshot()["devices"]["valve"]
    assert state["status"] == "unknown"
    assert state["picture"] is None
    assert "doesn't say where the rotor is" in state["error"]


def test_a_broken_deriver_makes_the_state_unknown_without_failing_the_command():
    store = DeviceStateStore(["valve"], deriver=_Deriver())
    observer = store.observer()

    observer(_event("started", params={"connect": "boom"}))
    observer(_event("finished"))

    state = store.snapshot()["devices"]["valve"]
    assert state["status"] == "unknown"
    assert "deriver bug" in state["error"]


def test_a_command_to_a_device_not_in_the_project_still_gets_a_record():
    store = DeviceStateStore([])

    store.observer()(_event("started", component="extra"))

    assert store.snapshot()["devices"]["extra"]["status"] == "running"


# ── change log ───────────────────────────────────────────────────────────────


def test_changes_since_returns_each_change_in_order():
    store = DeviceStateStore(["valve"])
    observer = store.observer()
    observer(_event("started"))
    observer(_event("finished"))

    changes = store.changes_since(0)

    assert [change["seq"] for change in changes] == [1, 2]
    assert [change["devices"]["valve"]["status"] for change in changes] == [
        "running",
        "done",
    ]
    assert store.changes_since(1) == changes[1:]
    assert store.changes_since(2) == []


@pytest.mark.parametrize("seq", [3, 100])
def test_changes_since_a_seq_the_store_never_reached_needs_a_snapshot(seq):
    store = DeviceStateStore(["valve"])
    store.observer()(_event("started"))
    store.observer()(_event("finished"))

    assert store.changes_since(seq) is None


def test_changes_since_needs_a_snapshot_once_the_log_has_moved_on():
    store = DeviceStateStore(["valve"], log_size=2)
    observer = store.observer()
    for call_id in (1, 2):
        observer(_event("started", call_id=call_id))
        observer(_event("finished", call_id=call_id))

    assert store.changes_since(1) is None
    assert [change["seq"] for change in store.changes_since(2)] == [3, 4]


def test_each_store_has_its_own_epoch():
    assert DeviceStateStore().epoch != DeviceStateStore().epoch


# ── LCD displays ─────────────────────────────────────────────────────────────


def _lcd_store(monitored=("pump::value",)):
    return DeviceStateStore(
        ["pump"],
        displays={"Flow": "pump::value", "Other": 'adc::read::{"channel":2}'},
        monitored_keys=lambda: set(monitored),
    )


def test_every_lcd_starts_without_a_reading():
    displays = _lcd_store().snapshot()["displays"]

    assert displays == {
        "Flow": {"value": None, "at": None, "error": None, "monitored": True},
        "Other": {"value": None, "at": None, "error": None, "monitored": False},
    }


@pytest.mark.parametrize(
    ("value", "text"),
    [
        ("24.3456 °C", "24.3456 °C"),
        (1.5, "1.5"),
        (3, "3"),
        (True, "true"),
        ({"value": 2, "unit": "bar"}, '{"value": 2, "unit": "bar"}'),
    ],
)
def test_a_reading_shows_on_its_lcds_as_text(value, text):
    store = _lcd_store()

    store.record_reading("pump::value", {"time": "t1", "value": value, "error": None})

    assert store.snapshot()["displays"]["Flow"] == {
        "value": text,
        "at": "t1",
        "error": None,
        "monitored": True,
    }
    (change,) = store.changes_since(0)
    assert change["displays"]["Flow"]["value"] == text


def test_a_failed_reading_shows_no_value_and_the_reason():
    store = _lcd_store()

    store.record_reading(
        "pump::value", {"time": "t1", "value": None, "error": "timeout"}
    )

    display = store.snapshot()["displays"]["Flow"]
    assert (display["value"], display["error"]) == (None, "timeout")


def test_readings_of_variables_no_lcd_shows_change_nothing():
    store = _lcd_store()

    store.record_reading("valve::position", {"time": "t", "value": 1, "error": None})

    assert store.seq == 0
