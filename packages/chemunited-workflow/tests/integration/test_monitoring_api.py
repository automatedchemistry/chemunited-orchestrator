"""Integration tests for the /monitoring routes."""

from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import responses as resp_lib
from fastapi.testclient import TestClient

from chemunited_workflow.api import create_api
from tests.helpers import make_project_tree

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def project(tmp_path):
    dirs = make_project_tree(tmp_path)
    (dirs["connectivity_dir"] / "associations.json").write_text(
        (FIXTURES / "associations.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return {"dirs": dirs, "tmp_path": tmp_path}


@pytest.fixture
def holder(project):
    from chemunited_workflow.api.dependencies import get_project_holder
    from chemunited_workflow.project_loader import ProjectModules

    proc_dir = project["dirs"]["process_dir"]
    mod = _load_module(proc_dir / "my_process.py", "my_process_monitoring")
    main_mod = _load_module(
        proc_dir / "main_parameters.py", "main_parameters_monitoring"
    )

    api = create_api()
    h = api.dependency_overrides[get_project_holder]()
    h.load(
        ProjectModules(
            project_dir=project["tmp_path"],
            processes={"my_process": mod.MyProcess},
            configs={"my_process": mod.MyConfig},
            main_parameter_class=main_mod.MainParameter,
        )
    )
    h._api = api
    return h


@pytest.fixture
def app(holder):
    return holder._api


@pytest.fixture
def client(app):
    return TestClient(app)


def _wait_until(predicate, timeout=2.0, interval=0.02):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


# ── /monitoring/discover ─────────────────────────────────────────────────────


def test_discover_returns_get_commands(client, mocker):
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "paths": {
            "/sim-ml600/pump/value": {"get": {"summary": "Read value"}},
            "/sim-ml600/pump/dose": {"put": {"summary": "Dose"}},
        }
    }
    mocker.patch(
        "chemunited_workflow.api.services.monitoring.requests.get",
        return_value=mock_resp,
    )
    r = client.get("/monitoring/discover/pump")
    assert r.status_code == 200
    assert r.json() == [{"command": "value", "summary": "Read value", "parameters": []}]


def test_discover_unknown_component_404(client):
    r = client.get("/monitoring/discover/ghost")
    assert r.status_code == 404


def test_discover_unreachable_server_502(client, mocker):
    import requests as req

    mocker.patch(
        "chemunited_workflow.api.services.monitoring.requests.get",
        side_effect=req.exceptions.ConnectionError("refused"),
    )
    r = client.get("/monitoring/discover/pump")
    assert r.status_code == 502


def test_discover_sila2_unreachable_502(client, project, mocker):
    import json as _json

    associations_path = project["dirs"]["connectivity_dir"] / "associations.json"
    data = _json.loads(associations_path.read_text(encoding="utf-8"))
    data["associations"].append(
        {
            "component": "sila-pump",
            "protocol": "sila2",
            "sila_host": "localhost",
            "sila_port": 50996,
            "sila_insecure": True,
        }
    )
    associations_path.write_text(_json.dumps(data), encoding="utf-8")
    mocker.patch(
        "chemunited_workflow.clients.sila.SilaClient",
        side_effect=ConnectionError("refused"),
    )

    r = client.get("/monitoring/discover/sila-pump")

    assert r.status_code == 502
    assert "discovery failed" in r.json()["detail"]


# ── /monitoring/config ───────────────────────────────────────────────────────


def test_get_config_defaults(client):
    r = client.get("/monitoring/config")
    assert r.status_code == 200
    assert r.json()["variables"] == []


def test_put_config_persists(client, project):
    body = {
        "sample_time": 0.05,
        "request_timeout": 1.0,
        "variables": [{"component": "pump", "command": "value", "kwargs": {}}],
    }
    r = client.put("/monitoring/config", json=body)
    assert r.status_code == 200
    assert r.json()["variables"][0]["component"] == "pump"
    assert (project["dirs"]["connectivity_dir"] / "monitoring.json").exists()


# ── /monitoring/state, /start, /stop, /latest, /history ─────────────────────


def test_initial_state_is_off(client):
    r = client.get("/monitoring/state")
    assert r.status_code == 200
    assert r.json() == {
        "manual_on": False,
        "run_active": False,
        "recording": False,
        "run_id": None,
        "effective_on": False,
    }


def test_start_without_config_422(client):
    r = client.post("/monitoring/start")
    assert r.status_code == 422


@resp_lib.activate
def test_manual_start_stop_lifecycle(client):
    resp_lib.add(
        resp_lib.GET,
        "http://device-server:8000/sim-ml600/pump/value",
        json=99.0,
        status=200,
    )

    client.put(
        "/monitoring/config",
        json={
            "sample_time": 0.05,
            "request_timeout": 1.0,
            "variables": [{"component": "pump", "command": "value", "kwargs": {}}],
        },
    )

    start = client.post("/monitoring/start")
    assert start.status_code == 200
    assert start.json()["effective_on"] is True

    assert _wait_until(lambda: client.get("/monitoring/latest").json() != {})

    latest = client.get("/monitoring/latest").json()
    assert latest["pump::value"]["value"] == 99.0

    state = client.get("/monitoring/state")
    assert state.json()["manual_on"] is True

    history = client.get("/monitoring/history/pump/value")
    assert history.status_code == 200
    assert history.json()[-1]["value"] == 99.0

    stop = client.post("/monitoring/stop")
    assert stop.status_code == 200
    assert stop.json()["effective_on"] is False


def test_start_is_idempotent(client):
    client.put(
        "/monitoring/config",
        json={
            "sample_time": 1.0,
            "request_timeout": 1.0,
            "variables": [{"component": "pump", "command": "value", "kwargs": {}}],
        },
    )
    first = client.post("/monitoring/start")
    second = client.post("/monitoring/start")
    assert first.status_code == 200
    assert second.status_code == 200
    client.post("/monitoring/stop")


def test_stop_is_idempotent(client):
    first = client.post("/monitoring/stop")
    assert first.status_code == 200
    assert first.json()["effective_on"] is False


def test_latest_empty_when_never_polled(client):
    r = client.get("/monitoring/latest")
    assert r.status_code == 200
    assert r.json() == {}


def test_history_empty_for_unpolled_variable(client):
    r = client.get("/monitoring/history/pump/value")
    assert r.status_code == 200
    assert r.json() == []


def test_start_stop_409_while_run_active(client, holder):
    holder.monitoring_service.on_run_started("run-1", record=False)
    try:
        start = client.post("/monitoring/start")
        assert start.status_code == 409
        stop = client.post("/monitoring/stop")
        assert stop.status_code == 409
    finally:
        holder.monitoring_service.on_run_finished()


# ── /monitoring/recordings ───────────────────────────────────────────────────


def test_recording_missing_404(client):
    r = client.get("/monitoring/recordings/no-such-run/pump/value")
    assert r.status_code == 404


@resp_lib.activate
def test_recorded_run_profile_is_readable(client, holder):
    resp_lib.add(
        resp_lib.GET,
        "http://device-server:8000/sim-ml600/pump/value",
        json=55.0,
        status=200,
    )
    client.put(
        "/monitoring/config",
        json={
            "sample_time": 0.02,
            "request_timeout": 1.0,
            "variables": [{"component": "pump", "command": "value", "kwargs": {}}],
        },
    )
    holder.monitoring_service.on_run_started("run-1", record=True)
    try:
        assert _wait_until(lambda: holder.monitoring_service.get_latest() != {})
    finally:
        holder.monitoring_service.on_run_finished()

    r = client.get("/monitoring/recordings/run-1/pump/value")
    assert r.status_code == 200
    readings = r.json()
    assert len(readings) >= 1
    assert readings[0]["value"] == 55.0

    tailed = client.get("/monitoring/recordings/run-1/pump/value?tail=1")
    assert len(tailed.json()) == 1
