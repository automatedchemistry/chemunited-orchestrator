"""Unit tests for MonitoringService."""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

import pytest
import requests
import responses as resp_lib

from chemunited_workflow.api.monitoring_store import MonitoringStore
from chemunited_workflow.api.services.monitoring import MonitoringService
from chemunited_workflow.exceptions import MonitoringRunActiveError
from chemunited_workflow.monitoring_context import MonitoringContext
from chemunited_workflow.platform import Platform

_MODULE = "chemunited_workflow.api.services.monitoring.requests"


@pytest.fixture(autouse=True)
def _reset_monitoring_context():
    yield
    MonitoringContext.platform = None


@pytest.fixture
def svc(tmp_path):
    (tmp_path / "connectivity").mkdir()
    (tmp_path / "log").mkdir()

    assoc = {
        "server_url": "http://device-server:8000",
        "associations": [
            {"component": "pump", "component_url": "sim/pump"},
            {"component": "valve", "component_url": "sim/valve"},
            {"component": "empty", "component_url": ""},
            {
                "component": "sila-pump",
                "protocol": "sila2",
                "sila_host": "localhost",
                "sila_port": 50998,
                "sila_insecure": True,
            },
            {
                "component": "opc-valve",
                "protocol": "opcua",
                "opcua_endpoint": "opc.tcp://localhost:4998",
                "opcua_node_id": "ns=2;s=Root",
            },
        ],
    }
    (tmp_path / "connectivity" / "associations.json").write_text(
        json.dumps(assoc), encoding="utf-8"
    )
    return MonitoringService(project_dir=tmp_path, store=MonitoringStore())


@pytest.fixture
def platform(svc):
    platform = Platform.from_project_dir(svc._project_dir, error_resilient=True)
    yield platform
    for client in platform.values():
        client.close()


def _openapi_response(paths: dict) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"paths": paths}
    return resp


# ── discover ─────────────────────────────────────────────────────────────────


def test_discover_filters_to_component_get_paths(svc):
    paths = {
        "/sim/pump/value": {"get": {"summary": "Read value", "parameters": []}},
        "/sim/pump/dose": {"put": {"summary": "Dose"}},
        "/sim/valve/position": {"get": {"summary": "Read position"}},
    }
    with patch(f"{_MODULE}.get", return_value=_openapi_response(paths)):
        result = svc.discover("pump")
    assert result == [{"command": "value", "summary": "Read value", "parameters": []}]


def test_discover_unknown_component_raises_keyerror(svc):
    with pytest.raises(KeyError):
        svc.discover("ghost")


def test_discover_works_without_top_level_server_url(tmp_path):
    """New associations.json format: no top-level server_url, component_url
    is already absolute. discover() must derive the openapi.json root/prefix
    from the resolved client.base_url instead."""
    (tmp_path / "connectivity").mkdir()
    (tmp_path / "log").mkdir()
    assoc = {
        "associations": [
            {
                "component": "pump",
                "component_url": "http://device-server:8000/sim/pump",
            },
        ]
    }
    (tmp_path / "connectivity" / "associations.json").write_text(
        json.dumps(assoc), encoding="utf-8"
    )
    svc = MonitoringService(project_dir=tmp_path, store=MonitoringStore())

    paths = {
        "/sim/pump/value": {"get": {"summary": "Read value", "parameters": []}},
        "/sim/pump/dose": {"put": {"summary": "Dose"}},
    }
    with patch(f"{_MODULE}.get", return_value=_openapi_response(paths)) as get_spy:
        result = svc.discover("pump")

    get_spy.assert_called_once_with(
        "http://device-server:8000/openapi.json", timeout=5.0
    )
    assert result == [{"command": "value", "summary": "Read value", "parameters": []}]


def test_discover_propagates_request_exception(svc):
    with patch(
        f"{_MODULE}.get", side_effect=requests.exceptions.ConnectionError("refused")
    ):
        with pytest.raises(requests.exceptions.ConnectionError):
            svc.discover("pump")


def test_discover_sila2_filters_to_get_entries(mocker, svc):
    from tests.unit.test_clients_sila import (
        FakeCommand,
        FakeFeature,
        FakeProperty,
        FakeSilaClient,
    )

    feature = FakeFeature(
        "Thermostat",
        properties={"Temperature": FakeProperty("Temperature", value=21.5)},
        commands={"SetPoint": FakeCommand("SetPoint")},
    )

    def build_and_inject(*args, **kwargs):
        client = FakeSilaClient(*args, **kwargs)
        client._features[feature._identifier] = feature
        return client

    mocker.patch(
        "chemunited_workflow.clients.sila.SilaClient", side_effect=build_and_inject
    )

    result = svc.discover("sila-pump")

    commands = {entry["command"] for entry in result}
    assert commands == {"Thermostat.Temperature"}  # SetPoint is a put, filtered out


def test_discover_opcua_filters_to_get_entries(mocker, svc):
    from asyncua import ua

    from tests.unit.test_clients_opcua import FakeClient, FakeNode

    readonly_var = FakeNode(browse_name=ua.QualifiedName("Status", 2), writable=False)
    root = FakeNode(children={"2:Status": readonly_var})

    def build_and_inject(endpoint):
        client = FakeClient(endpoint)
        client._root = root
        return client

    mocker.patch(
        "chemunited_workflow.clients.opcua.Client", side_effect=build_and_inject
    )

    result = svc.discover("opc-valve")

    commands = {entry["command"] for entry in result}
    assert commands == {"2:Status"}


@resp_lib.activate
def test_discover_closes_client(svc, mocker):
    resp_lib.add(
        resp_lib.GET,
        "http://device-server:8000/openapi.json",
        json={"paths": {}},
        status=200,
    )
    close_spy = mocker.patch("chemunited_workflow.clients.http.BaseClient.close")
    svc.discover("pump")
    close_spy.assert_called_once()


# ── config ───────────────────────────────────────────────────────────────────


def test_read_config_defaults_when_missing(svc):
    config = svc.read_config()
    assert config["variables"] == []
    assert config["sample_time"] > 0


def test_write_then_read_config_round_trips(svc):
    svc.write_config(
        {
            "sample_time": 2.0,
            "request_timeout": 3.0,
            "variables": [{"component": "pump", "command": "value", "kwargs": {}}],
        }
    )
    config = svc.read_config()
    assert config["sample_time"] == 2.0
    assert config["variables"][0]["component"] == "pump"


# ── _fetch_one ───────────────────────────────────────────────────────────────


@resp_lib.activate
def test_fetch_one_success(svc, platform):
    resp_lib.add(
        resp_lib.GET, "http://device-server:8000/sim/pump/value", json=23.5, status=200
    )
    reading = svc._fetch_one(platform, "pump", "value", {})
    assert reading["value"] == 23.5
    assert reading["error"] is None


@resp_lib.activate
def test_fetch_one_request_exception_sets_error(svc, platform):
    resp_lib.add(
        resp_lib.GET,
        "http://device-server:8000/sim/pump/value",
        body=requests.exceptions.Timeout("slow"),
    )
    reading = svc._fetch_one(platform, "pump", "value", {})
    assert reading["value"] is None
    assert "slow" in reading["error"]


@resp_lib.activate
def test_fetch_one_unknown_component_does_not_call_requests(svc, platform):
    reading = svc._fetch_one(platform, "ghost", "value", {})
    assert len(resp_lib.calls) == 0
    assert reading["value"] is None
    assert reading["error"] is not None


def test_fetch_one_sila2_success(mocker, svc, platform):
    from tests.unit.test_clients_sila import FakeFeature, FakeProperty, FakeSilaClient

    mocker.patch("chemunited_workflow.clients.sila.SilaClient", FakeSilaClient)
    feature = FakeFeature(
        "Thermostat",
        properties={"Temperature": FakeProperty("Temperature", value=21.5)},
    )
    client = platform["sila-pump"]
    client._ensure_connected()
    client._client._features[feature._identifier] = feature

    reading = svc._fetch_one(platform, "sila-pump", "Thermostat.Temperature", {})

    assert reading["value"] == 21.5
    assert reading["error"] is None


def test_fetch_one_sila2_device_error(mocker, svc, platform):
    from tests.unit.test_clients_sila import FakeFeature, FakeProperty, FakeSilaClient

    mocker.patch("chemunited_workflow.clients.sila.SilaClient", FakeSilaClient)
    feature = FakeFeature(
        "Thermostat",
        properties={
            "Temperature": FakeProperty("Temperature", error=RuntimeError("offline"))
        },
    )
    client = platform["sila-pump"]
    client._ensure_connected()
    client._client._features[feature._identifier] = feature

    reading = svc._fetch_one(platform, "sila-pump", "Thermostat.Temperature", {})

    assert reading["value"] is None
    assert "offline" in reading["error"]


# ── manual on/off ────────────────────────────────────────────────────────────


def test_start_without_variables_raises(svc):
    with pytest.raises(ValueError):
        svc.start()


def _wait_until(predicate, timeout=2.0, interval=0.02):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


@resp_lib.activate
def test_manual_start_polls_updates_state_without_writing_files(svc, tmp_path):
    resp_lib.add(
        resp_lib.GET, "http://device-server:8000/sim/pump/value", json=42.0, status=200
    )
    svc.write_config(
        {
            "sample_time": 0.05,
            "request_timeout": 1.0,
            "variables": [{"component": "pump", "command": "value", "kwargs": {}}],
        }
    )
    svc.start()
    assert _wait_until(lambda: svc.get_latest() != {})
    svc.stop()

    latest = svc.get_latest()
    assert latest["pump::value"]["value"] == 42.0
    history = svc.get_history("pump", "value")
    assert history[-1]["value"] == 42.0

    # Manual-only monitoring must never touch disk — only a recorded run does.
    assert not (tmp_path / "log" / "monitoring").exists()


@resp_lib.activate
def test_one_device_failing_does_not_block_other(svc):
    resp_lib.add(
        resp_lib.GET,
        "http://device-server:8000/sim/pump/value",
        body=requests.exceptions.Timeout("pump hung"),
    )
    resp_lib.add(
        resp_lib.GET,
        "http://device-server:8000/sim/valve/position",
        json="open",
        status=200,
    )
    svc.write_config(
        {
            "sample_time": 0.05,
            "request_timeout": 1.0,
            "variables": [
                {"component": "pump", "command": "value", "kwargs": {}},
                {"component": "valve", "command": "position", "kwargs": {}},
            ],
        }
    )
    svc.start()
    assert _wait_until(
        lambda: "pump::value" in svc.get_latest()
        and "valve::position" in svc.get_latest()
    )
    svc.stop()

    latest = svc.get_latest()
    assert latest["pump::value"]["error"] is not None
    assert latest["pump::value"]["value"] is None
    assert latest["valve::position"]["error"] is None
    assert latest["valve::position"]["value"] == "open"


@resp_lib.activate
def test_two_variables_same_component_poll_sequentially(svc):
    """Two monitored variables on the same component must share one client and
    never be dispatched to two pool workers in the same tick — that would trip
    ComponentClient's non-blocking per-device lock (ConcurrentClientAccessError),
    same as two protocol-run nodes hitting one device concurrently would.
    """
    resp_lib.add(
        resp_lib.GET, "http://device-server:8000/sim/pump/value", json=1.0, status=200
    )
    resp_lib.add(
        resp_lib.GET, "http://device-server:8000/sim/pump/rate", json=2.0, status=200
    )
    svc.write_config(
        {
            "sample_time": 0.05,
            "variables": [
                {"component": "pump", "command": "value", "kwargs": {}},
                {"component": "pump", "command": "rate", "kwargs": {}},
            ],
        }
    )
    svc.start()
    assert _wait_until(
        lambda: "pump::value" in svc.get_latest() and "pump::rate" in svc.get_latest()
    )
    svc.stop()

    latest = svc.get_latest()
    assert latest["pump::value"]["error"] is None
    assert latest["pump::value"]["value"] == 1.0
    assert latest["pump::rate"]["error"] is None
    assert latest["pump::rate"]["value"] == 2.0


@resp_lib.activate
def test_manual_toggle_closes_each_client_once_not_per_tick(svc, mocker):
    resp_lib.add(
        resp_lib.GET, "http://device-server:8000/sim/pump/value", json=1.0, status=200
    )
    close_spy = mocker.patch("chemunited_workflow.clients.http.BaseClient.close")
    svc.write_config(
        {
            "sample_time": 0.02,
            "variables": [{"component": "pump", "command": "value", "kwargs": {}}],
        }
    )
    svc.start()
    # let several ticks elapse
    assert _wait_until(lambda: svc.get_latest() != {})
    time.sleep(0.15)
    svc.stop()
    # stop() clears manual_on synchronously, before the background thread
    # actually exits its loop and runs cleanup — wait for the real signal
    # (close() firing) instead of the state flag.
    assert _wait_until(lambda: close_spy.call_count >= 2)

    # Once per registered flowchem component (pump + valve; sila-pump/opc-valve use
    # a different client class), regardless of how many ticks elapsed — not per-tick.
    assert close_spy.call_count == 2


def test_start_raises_while_run_active(svc):
    svc.on_run_started("run-1", record=False)
    with pytest.raises(MonitoringRunActiveError):
        svc.start()
    svc.on_run_finished()


@resp_lib.activate
def test_stop_raises_while_run_active(svc):
    resp_lib.add(
        resp_lib.GET, "http://device-server:8000/sim/pump/value", json=1.0, status=200
    )
    svc.write_config(
        {
            "sample_time": 1.0,
            "variables": [{"component": "pump", "command": "value", "kwargs": {}}],
        }
    )
    svc.start()
    svc.on_run_started("run-1", record=False)
    with pytest.raises(MonitoringRunActiveError):
        svc.stop()
    svc.on_run_finished()
    svc.stop()


# ── run-lifecycle hooks ──────────────────────────────────────────────────────


@resp_lib.activate
def test_on_run_started_forces_on_and_writes_recording(svc, tmp_path):
    resp_lib.add(
        resp_lib.GET, "http://device-server:8000/sim/pump/value", json=7.0, status=200
    )
    svc.write_config(
        {
            "sample_time": 0.05,
            "variables": [{"component": "pump", "command": "value", "kwargs": {}}],
        }
    )
    svc.on_run_started("run-1", record=True)
    assert svc.get_state()["run_active"] is True
    assert svc.get_state()["recording"] is True

    run_dir = tmp_path / "log" / "monitoring" / "run-1"
    assert _wait_until(lambda: run_dir.exists() and any(run_dir.iterdir()))
    svc.on_run_finished()

    recording = svc.read_recording("run-1", "pump", "value")
    assert recording[0]["value"] == 7.0


@resp_lib.activate
def test_non_recorded_run_writes_no_files(svc, tmp_path):
    resp_lib.add(
        resp_lib.GET, "http://device-server:8000/sim/pump/value", json=7.0, status=200
    )
    svc.write_config(
        {
            "sample_time": 0.02,
            "variables": [{"component": "pump", "command": "value", "kwargs": {}}],
        }
    )
    svc.on_run_started("run-1", record=False)
    assert _wait_until(lambda: svc.get_latest() != {})
    time.sleep(0.1)
    svc.on_run_finished()

    assert not (tmp_path / "log" / "monitoring").exists()


@resp_lib.activate
def test_on_run_started_when_already_manual_on_reuses_existing_thread(svc, mocker):
    resp_lib.add(
        resp_lib.GET, "http://device-server:8000/sim/pump/value", json=1.0, status=200
    )
    close_spy = mocker.patch("chemunited_workflow.clients.http.BaseClient.close")
    svc.write_config(
        {
            "sample_time": 0.02,
            "variables": [{"component": "pump", "command": "value", "kwargs": {}}],
        }
    )
    svc.start()
    assert _wait_until(lambda: svc.get_latest() != {})

    svc.on_run_started("run-1", record=True)
    assert svc.get_state()["recording"] is True
    time.sleep(0.1)
    svc.on_run_finished()
    # manual_on was already true, so ending the run must not stop the loop.
    assert svc.get_state()["effective_on"] is True
    svc.stop()

    assert _wait_until(lambda: close_spy.call_count >= 2)
    # Once per registered flowchem component (pump + valve; sila-pump/opc-valve
    # use a different client class) from the single platform teardown — if a
    # second thread had been spawned for the run, this would double to 4.
    assert close_spy.call_count == 2


@resp_lib.activate
def test_on_run_finished_stops_loop_when_manual_was_off(svc, mocker):
    resp_lib.add(
        resp_lib.GET, "http://device-server:8000/sim/pump/value", json=1.0, status=200
    )
    close_spy = mocker.patch("chemunited_workflow.clients.http.BaseClient.close")
    svc.write_config(
        {
            "sample_time": 0.02,
            "variables": [{"component": "pump", "command": "value", "kwargs": {}}],
        }
    )
    svc.on_run_started("run-1", record=False)
    assert _wait_until(lambda: svc.get_latest() != {})
    svc.on_run_finished()

    assert svc.get_state()["effective_on"] is False
    assert _wait_until(lambda: close_spy.call_count >= 1)


def test_on_run_started_record_true_with_no_variables_warns_without_raising(
    svc, tmp_path
):
    svc.on_run_started("run-1", record=True)  # must not raise
    time.sleep(0.05)
    svc.on_run_finished()
    assert not (tmp_path / "log" / "monitoring" / "run-1").exists()


def test_on_run_started_and_finished_never_raise_on_internal_error(svc):
    # Simulate a broken config file — on_run_started must swallow the error.
    svc._config_path.parent.mkdir(parents=True, exist_ok=True)
    svc._config_path.write_text("not json", encoding="utf-8")
    svc.on_run_started("run-1", record=True)  # must not raise
    svc.on_run_finished()  # must not raise


# ── read_recording / get_latest / get_history ───────────────────────────────


def test_read_recording_missing_raises(svc):
    with pytest.raises(FileNotFoundError):
        svc.read_recording("no-such-run", "pump", "value")


def test_get_latest_starts_empty(svc):
    assert svc.get_latest() == {}


def test_get_history_unknown_variable_returns_empty_list(svc):
    assert svc.get_history("pump", "value") == []


# ── custom sources ───────────────────────────────────────────────────────────


def _write_hook(tmp_path, body: str) -> None:
    hook_dir = tmp_path / "customizations" / "monitoring"
    hook_dir.mkdir(parents=True, exist_ok=True)
    (hook_dir / "monitoring_hook.py").write_text(body, encoding="utf-8")


def test_group_key_real_component_uses_component_name():
    var = {"component": "pump", "command": "value"}
    assert MonitoringService._group_key(var) == "pump"


def test_group_key_different_custom_sources_get_different_keys():
    a = MonitoringService._group_key({"component": "custom", "command": "fn1"})
    b = MonitoringService._group_key({"component": "custom", "command": "fn2"})
    assert a != b


def test_group_key_same_custom_source_shares_key():
    a = MonitoringService._group_key(
        {"component": "custom", "command": "fn", "kwargs": {"x": 1}}
    )
    b = MonitoringService._group_key(
        {"component": "custom", "command": "fn", "kwargs": {"x": 2}}
    )
    assert a == b


def test_load_custom_sources_missing_file_returns_empty(svc):
    assert svc._load_custom_sources() == {}


def test_load_custom_sources_loads_registered_dict(svc, tmp_path):
    _write_hook(tmp_path, "CUSTOM_SOURCES = {'double': lambda x: x * 2}\n")
    sources = svc._load_custom_sources()
    assert set(sources) == {"double"}
    assert sources["double"](x=3) == 6


def test_load_custom_sources_missing_export_returns_empty(svc, tmp_path):
    _write_hook(tmp_path, "NOT_THE_RIGHT_NAME = {}\n")
    assert svc._load_custom_sources() == {}


def test_load_custom_sources_broken_file_returns_empty_without_raising(svc, tmp_path):
    _write_hook(tmp_path, "raise RuntimeError('boom')\n")
    assert svc._load_custom_sources() == {}


def test_fetch_one_custom_source_success(svc, platform):
    reading = svc._fetch_one(
        platform, "custom", "double", {"x": 3}, {"double": lambda x: x * 2}
    )
    assert reading["value"] == 6
    assert reading["error"] is None


def test_fetch_one_custom_source_unregistered_sets_error(svc, platform):
    reading = svc._fetch_one(platform, "custom", "ghost", {}, {})
    assert reading["value"] is None
    assert "not registered" in reading["error"]


def test_fetch_one_custom_source_exception_sets_error_without_raising(svc, platform):
    def boom(**kwargs):
        raise ValueError("bad reading")

    reading = svc._fetch_one(platform, "custom", "boom", {}, {"boom": boom})
    assert reading["value"] is None
    assert "bad reading" in reading["error"]


def test_discover_custom_lists_registered_sources(svc, tmp_path):
    _write_hook(
        tmp_path, "CUSTOM_SOURCES = {'double': lambda x: x * 2, 'triple': None}\n"
    )
    result = svc.discover("custom")
    assert {entry["command"] for entry in result} == {"double", "triple"}


def test_discover_custom_empty_when_no_hook_file(svc):
    assert svc.discover("custom") == []


@resp_lib.activate
def test_manual_start_polls_custom_source(svc, tmp_path):
    _write_hook(tmp_path, "CUSTOM_SOURCES = {'derived': lambda: 99}\n")
    svc.write_config(
        {
            "sample_time": 0.05,
            "variables": [{"component": "custom", "command": "derived", "kwargs": {}}],
        }
    )
    svc.start()
    assert _wait_until(lambda: "custom::derived" in svc.get_latest())
    svc.stop()

    latest = svc.get_latest()
    assert latest["custom::derived"]["value"] == 99
    assert latest["custom::derived"]["error"] is None


@resp_lib.activate
def test_custom_source_does_not_block_real_component_poll(svc, tmp_path):
    """A custom source and a real component must poll independently — neither
    ever waits on the other's pool worker."""
    resp_lib.add(
        resp_lib.GET, "http://device-server:8000/sim/pump/value", json=1.0, status=200
    )
    _write_hook(tmp_path, "CUSTOM_SOURCES = {'derived': lambda: 99}\n")
    svc.write_config(
        {
            "sample_time": 0.05,
            "variables": [
                {"component": "pump", "command": "value", "kwargs": {}},
                {"component": "custom", "command": "derived", "kwargs": {}},
            ],
        }
    )
    svc.start()
    assert _wait_until(
        lambda: "pump::value" in svc.get_latest()
        and "custom::derived" in svc.get_latest()
    )
    svc.stop()

    latest = svc.get_latest()
    assert latest["pump::value"]["value"] == 1.0
    assert latest["custom::derived"]["value"] == 99


# ── MonitoringContext (platform access for custom sources) ─────────────────


def test_monitoring_context_platform_none_before_start():
    assert MonitoringContext.platform is None


@resp_lib.activate
def test_manual_start_sets_monitoring_context_platform(svc):
    resp_lib.add(
        resp_lib.GET, "http://device-server:8000/sim/pump/value", json=1.0, status=200
    )
    svc.write_config(
        {
            "sample_time": 0.05,
            "variables": [{"component": "pump", "command": "value", "kwargs": {}}],
        }
    )
    svc.start()
    assert _wait_until(lambda: MonitoringContext.platform is not None)
    svc.stop()
    assert _wait_until(lambda: MonitoringContext.platform is None)


@resp_lib.activate
def test_fetch_one_custom_source_reads_real_component_via_monitoring_context(
    svc, platform
):
    resp_lib.add(
        resp_lib.GET, "http://device-server:8000/sim/pump/value", json=5.0, status=200
    )
    MonitoringContext.platform = platform

    def fn(**kwargs):
        return MonitoringContext.platform["pump"].get("value") * 2

    reading = svc._fetch_one(platform, "custom", "fn", {}, {"fn": fn})
    assert reading["value"] == 10.0
    assert reading["error"] is None


def test_fetch_one_custom_source_monitoring_context_none_sets_error(svc, platform):
    assert MonitoringContext.platform is None

    def fn(**kwargs):
        return MonitoringContext.platform["pump"].get("value")

    reading = svc._fetch_one(platform, "custom", "fn", {}, {"fn": fn})
    assert reading["value"] is None
    assert reading["error"] is not None


def test_fetch_one_custom_source_concurrent_access_caught_as_error_reading(
    svc, platform
):
    """A custom source reading a component another pool worker is mid-fetching
    in the same tick trips ComponentClient's non-blocking per-device lock —
    this must be caught like any other exception, never propagate and kill
    the pool worker."""
    MonitoringContext.platform = platform
    client = platform["pump"]
    assert client._access_lock.acquire(blocking=False)
    try:

        def fn(**kwargs):
            return MonitoringContext.platform["pump"].get("value")

        reading = svc._fetch_one(platform, "custom", "fn", {}, {"fn": fn})
    finally:
        client._access_lock.release()

    assert reading["value"] is None
    assert "simultaneously" in reading["error"]


@resp_lib.activate
def test_manual_start_custom_source_reads_real_component_end_to_end(svc, tmp_path):
    resp_lib.add(
        resp_lib.GET, "http://device-server:8000/sim/pump/value", json=21.0, status=200
    )
    _write_hook(
        tmp_path,
        "from chemunited_workflow import MonitoringContext\n"
        "\n"
        "def pump_value_doubled(**kwargs):\n"
        "    return MonitoringContext.platform['pump'].get('value') * 2\n"
        "\n"
        "CUSTOM_SOURCES = {'pump_value_doubled': pump_value_doubled}\n",
    )
    svc.write_config(
        {
            "sample_time": 0.05,
            "variables": [
                {"component": "custom", "command": "pump_value_doubled", "kwargs": {}}
            ],
        }
    )
    svc.start()
    assert _wait_until(lambda: "custom::pump_value_doubled" in svc.get_latest())
    svc.stop()

    latest = svc.get_latest()
    assert latest["custom::pump_value_doubled"]["value"] == 42.0
    assert latest["custom::pump_value_doubled"]["error"] is None
