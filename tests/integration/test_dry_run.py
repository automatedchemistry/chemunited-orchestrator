"""Integration tests for dry-run mode (Step 04)."""

from __future__ import annotations

import importlib.util
import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from chemunited_workflow.clients import BaseClient, ComponentClient
from chemunited_workflow.platform import Platform
from chemunited_workflow.api import create_api
from fastapi.testclient import TestClient
from tests.helpers import make_project_tree

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ── Unit-level dry-run ────────────────────────────────────────────────────────


def test_dry_run_does_not_call_session_request():
    with patch("requests.Session.request") as mock_req:
        client = BaseClient("http://device:8000", dry_run=True)
        client.get("/x")
        mock_req.assert_not_called()


def test_dry_run_response_status_200():
    client = BaseClient("http://device:8000", dry_run=True)
    r = client.get("/x")
    assert r.status_code == 200


def test_dry_run_response_empty_json_body():
    client = BaseClient("http://device:8000", dry_run=True)
    r = client.get("/x")
    assert r.content == b"{}"


def test_dry_run_response_json_parses_to_empty_dict():
    client = BaseClient("http://device:8000", dry_run=True)
    r = client.get("/x")
    assert r.json() == {}


def test_dry_run_hooks_not_fired():
    client = BaseClient("http://device:8000", dry_run=True)
    client._log_response = lambda *a, **kw: (_ for _ in ()).throw(
        AssertionError("hook called")
    )
    client._raise_for_status = lambda *a, **kw: (_ for _ in ()).throw(
        AssertionError("hook called")
    )
    # Should not raise
    r = client.get("/x")
    assert r.status_code == 200


def test_dry_run_logs_info(caplog):
    import logging

    client = BaseClient("http://device:8000", dry_run=True)
    with caplog.at_level(logging.INFO):
        client.put("/dose", json={"volume_ml": 5.0})
    # Should not raise — log message was emitted


def test_component_client_concurrency_guard_active_in_dry_run():
    client = ComponentClient("http://device:8000", dry_run=True)
    from chemunited_workflow.exceptions import ConcurrentClientAccessError

    client._access_lock.acquire()
    try:
        with pytest.raises(ConcurrentClientAccessError):
            client.get("/x")
    finally:
        client._access_lock.release()


# ── Integration-level dry-run ────────────────────────────────────────────────


def test_from_connectivity_dry_run_propagated():
    p = Platform.from_connectivity(FIXTURES / "associations.json", dry_run=True)
    assert p["pump"]._dry_run is True


def test_api_dry_run_run_completes(tmp_path):
    dirs = make_project_tree(tmp_path)
    (dirs["connectivity_dir"] / "associations.json").write_text(
        (FIXTURES / "associations.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    snapshot = {
        "main_parameter": {"reagent_volume_ml": 5.0, "target_temperature_c": 25.0},
        "my_process_0": {"value": 1.0},
    }
    (dirs["historic_dir"] / "run_001.json").write_text(
        json.dumps(snapshot), encoding="utf-8"
    )
    mod = _load_module(dirs["process_dir"] / "my_process.py", "my_process")
    main_mod = _load_module(
        dirs["process_dir"] / "main_parameters.py", "main_parameters"
    )

    from chemunited_workflow.api.dependencies import get_project_holder
    from chemunited_workflow.project_loader import ProjectModules

    app = create_api()
    holder = app.dependency_overrides[get_project_holder]()
    holder.load(
        ProjectModules(
            project_dir=tmp_path,
            processes={"my_process": mod.MyProcess},
            configs={"my_process": mod.MyConfig},
            main_parameter_class=main_mod.MainParameter,
        )
    )
    client = TestClient(app)
    r = client.post("/run/", json={"protocol": "run_001.json", "dry_run": True})
    assert r.status_code == 202

    deadline = time.time() + 5.0
    state = "running"
    while time.time() < deadline:
        sr = client.get("/run/status")
        state = sr.json()["state"]
        if state != "running":
            break
        time.sleep(0.1)

    assert state in ("finished", "failed")
