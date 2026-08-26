"""Integration tests for record_monitoring linking a protocol run to monitoring."""

from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path

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
def holder(tmp_path):
    from chemunited_workflow.api.dependencies import get_project_holder
    from chemunited_workflow.project_loader import ProjectModules

    dirs = make_project_tree(tmp_path)
    (dirs["connectivity_dir"] / "associations.json").write_text(
        (FIXTURES / "associations.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (dirs["historic_dir"] / "run_monitoring.json").write_text(
        json.dumps({"main_parameter": {}, "my_process_0": {}}), encoding="utf-8"
    )

    mod = _load_module(
        dirs["process_dir"] / "my_process.py", "my_process_run_monitoring"
    )
    main_mod = _load_module(
        dirs["process_dir"] / "main_parameters.py", "main_parameters_run_monitoring"
    )

    api = create_api()
    h = api.dependency_overrides[get_project_holder]()
    h.load(
        ProjectModules(
            project_dir=tmp_path,
            processes={"my_process": mod.MyProcess},
            configs={"my_process": mod.MyConfig},
            main_parameter_class=main_mod.MainParameter,
        )
    )
    h._api = api
    h._tmp_path = tmp_path
    return h


@pytest.fixture
def client(holder):
    return TestClient(holder._api)


def _wait_until(predicate, timeout=5.0, interval=0.02):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


@resp_lib.activate
def test_recorded_run_persists_readings_under_run_id(client, holder):
    resp_lib.add(
        resp_lib.GET,
        "http://device-server:8000/sim-ml600/pump/value",
        json=1.0,
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

    r = client.post(
        "/run/",
        json={"protocol": "run_monitoring.json", "record_monitoring": True},
    )
    assert r.status_code == 202
    run_id = r.json()["run_id"]

    run_dir = holder._tmp_path / "log" / "monitoring" / run_id
    assert _wait_until(lambda: run_dir.exists() and any(run_dir.iterdir()))

    assert _wait_until(
        lambda: client.get("/run/status").json()["state"] in ("finished", "failed")
    )

    recording = client.get(f"/monitoring/recordings/{run_id}/pump/value")
    assert recording.status_code == 200
    assert recording.json()[0]["value"] == 1.0

    state = client.get("/monitoring/state").json()
    assert state["run_active"] is False
    assert state["effective_on"] is False


@resp_lib.activate
def test_non_recorded_run_does_not_create_monitoring_dir(client, holder):
    resp_lib.add(
        resp_lib.GET,
        "http://device-server:8000/sim-ml600/pump/value",
        json=1.0,
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

    r = client.post("/run/", json={"protocol": "run_monitoring.json"})
    assert r.status_code == 202

    assert _wait_until(
        lambda: client.get("/run/status").json()["state"] in ("finished", "failed")
    )
    time.sleep(0.1)

    assert not (holder._tmp_path / "log" / "monitoring").exists()


def test_record_monitoring_without_configured_variables_422(client, holder):
    r = client.post(
        "/run/",
        json={"protocol": "run_monitoring.json", "record_monitoring": True},
    )
    assert r.status_code == 422
    assert "no monitoring variables" in r.json()["detail"]

    # The run must never have started — no lockfile, no active run.
    assert client.get("/run/active").json()["active_run_id"] is None
    assert not (holder._tmp_path / "log" / "monitoring").exists()
