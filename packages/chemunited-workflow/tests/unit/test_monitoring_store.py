"""Unit tests for MonitoringStore — the singleton project-wide monitoring state."""

from __future__ import annotations

import pytest

from chemunited_workflow.api.monitoring_store import HISTORY_MAXLEN, MonitoringStore
from chemunited_workflow.exceptions import MonitoringRunActiveError


def test_initial_state_is_fully_off():
    store = MonitoringStore()
    snapshot = store.snapshot()
    assert snapshot == {
        "manual_on": False,
        "run_active": False,
        "recording": False,
        "run_id": None,
        "effective_on": False,
    }


# ── manual start/stop ────────────────────────────────────────────────────────


def test_try_manual_start_turns_on_and_returns_event():
    store = MonitoringStore()
    event = store.try_manual_start()
    assert event is not None
    assert not event.is_set()
    assert store.snapshot()["manual_on"] is True
    assert store.snapshot()["effective_on"] is True


def test_try_manual_start_idempotent_returns_none_second_time():
    store = MonitoringStore()
    store.try_manual_start()
    assert store.try_manual_start() is None


def test_try_manual_stop_turns_off_and_sets_event():
    store = MonitoringStore()
    event = store.try_manual_start()
    store.try_manual_stop()
    assert store.snapshot()["manual_on"] is False
    assert store.snapshot()["effective_on"] is False
    assert event.is_set()


def test_try_manual_stop_idempotent_noop_when_already_off():
    store = MonitoringStore()
    store.try_manual_stop()  # must not raise
    assert store.snapshot()["manual_on"] is False


def test_manual_start_raises_while_run_active():
    store = MonitoringStore()
    store.begin_run("run-1", record=False)
    with pytest.raises(MonitoringRunActiveError):
        store.try_manual_start()


def test_manual_stop_raises_while_run_active():
    store = MonitoringStore()
    store.try_manual_start()
    store.begin_run("run-1", record=False)
    with pytest.raises(MonitoringRunActiveError):
        store.try_manual_stop()


# ── run lifecycle ────────────────────────────────────────────────────────────


def test_begin_run_from_off_returns_event_and_forces_on():
    store = MonitoringStore()
    event = store.begin_run("run-1", record=True)
    assert event is not None
    snapshot = store.snapshot()
    assert snapshot["run_active"] is True
    assert snapshot["recording"] is True
    assert snapshot["run_id"] == "run-1"
    assert snapshot["effective_on"] is True


def test_begin_run_while_manual_on_returns_none_but_still_updates_state():
    store = MonitoringStore()
    store.try_manual_start()
    result = store.begin_run("run-1", record=True)
    assert result is None
    snapshot = store.snapshot()
    assert snapshot["run_active"] is True
    assert snapshot["recording"] is True
    assert snapshot["run_id"] == "run-1"


def test_end_run_stops_when_manual_was_off():
    store = MonitoringStore()
    event = store.begin_run("run-1", record=True)
    store.end_run()
    snapshot = store.snapshot()
    assert snapshot["run_active"] is False
    assert snapshot["recording"] is False
    assert snapshot["run_id"] is None
    assert snapshot["effective_on"] is False
    assert event.is_set()


def test_end_run_keeps_running_when_manual_was_already_on():
    store = MonitoringStore()
    manual_event = store.try_manual_start()
    store.begin_run("run-1", record=True)
    store.end_run()
    snapshot = store.snapshot()
    assert snapshot["run_active"] is False
    assert snapshot["recording"] is False
    assert snapshot["run_id"] is None
    assert (
        snapshot["effective_on"] is True
    )  # reverted to prior manual_on, not forced off
    assert not manual_event.is_set()


def test_poll_context_reflects_current_recording_and_run_id():
    store = MonitoringStore()
    assert store.poll_context() == (False, None)
    store.begin_run("run-1", record=True)
    assert store.poll_context() == (True, "run-1")
    store.end_run()
    assert store.poll_context() == (False, None)


# ── readings ─────────────────────────────────────────────────────────────────


def test_record_reading_updates_latest_and_history():
    store = MonitoringStore()
    store.record_reading("pump::value", {"time": "t0", "value": 1.0, "error": None})
    store.record_reading("pump::value", {"time": "t1", "value": 2.0, "error": None})
    assert store.get_latest()["pump::value"]["value"] == 2.0
    assert [r["value"] for r in store.get_history("pump::value")] == [1.0, 2.0]


def test_history_evicts_oldest_past_cap():
    store = MonitoringStore()
    for i in range(HISTORY_MAXLEN + 10):
        store.record_reading("pump::value", {"time": str(i), "value": i, "error": None})
    history = store.get_history("pump::value")
    assert len(history) == HISTORY_MAXLEN
    assert history[0]["value"] == 10
    assert history[-1]["value"] == HISTORY_MAXLEN + 9


def test_get_history_unknown_key_returns_empty_list():
    store = MonitoringStore()
    assert store.get_history("no-such-key") == []


def test_get_latest_starts_empty():
    store = MonitoringStore()
    assert store.get_latest() == {}
