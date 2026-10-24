"""Integration tests for the /platform routes (live platform view)."""

from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path

import pytest
import requests
from fastapi.testclient import TestClient
from tests.helpers import LOOPBACK_CLIENT, make_project_tree, write_source

from chemunited_workflow.api import create_api
from chemunited_workflow.api.dependencies import get_project_holder
from chemunited_workflow.clients import BaseClient
from chemunited_workflow.project_loader import ProjectModules

FIXTURES = Path(__file__).parent.parent / "fixtures"

DOSE_PROCESS_SRC = """
import networkx as nx
from pydantic import BaseModel
from chemunited_workflow import Process, NodeExecutionContext, WorkflowEdgeSpec, WorkflowNodeSpec

class DoseConfig(BaseModel):
    pass

class DoseProcess(Process):
    def build_workflow(self):
        g = nx.DiGraph()
        g.add_node("start", **WorkflowNodeSpec(node_id="start", method="start", label="Start").model_dump(exclude_none=True))
        g.add_node("finish", **WorkflowNodeSpec(node_id="finish", method="finish", label="Finish").model_dump(exclude_none=True))
        g.add_edge("start", "finish", **WorkflowEdgeSpec(condition=True).model_dump(exclude_none=True))
        return g
    def start(self, ctx: NodeExecutionContext) -> bool:
        self.platform["pump"].put("infuse", volume="1 ml")
        return True
    def finish(self, ctx: NodeExecutionContext) -> bool:
        return True
"""


def _load_module(path: Path, name: str, monkeypatch):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered so Process.load_parameters can find the module's file.
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


def _response(body: bytes = b"{}") -> requests.Response:
    response = requests.Response()
    response.status_code = 200
    response._content = body
    response.headers["Content-Type"] = "application/json"
    return response


@pytest.fixture
def modules(tmp_path, monkeypatch) -> ProjectModules:
    dirs = make_project_tree(tmp_path)
    (dirs["connectivity_dir"] / "associations.json").write_text(
        (FIXTURES / "associations.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    write_source(dirs["process_dir"], "dose_process.py", DOSE_PROCESS_SRC)
    (dirs["historic_dir"] / "dose_001.json").write_text(
        json.dumps(
            {
                "main_parameter": {
                    "reagent_volume_ml": 5.0,
                    "target_temperature_c": 25.0,
                },
                "dose_0": {},
            }
        ),
        encoding="utf-8",
    )
    process_dir = dirs["process_dir"]
    dose = _load_module(process_dir / "dose_process.py", "dose_process", monkeypatch)
    main = _load_module(process_dir / "main_parameters.py", "main_params", monkeypatch)

    return ProjectModules(
        project_dir=tmp_path,
        processes={"dose": dose.DoseProcess},
        configs={"dose": dose.DoseConfig},
        main_parameter_class=main.MainParameter,
    )


@pytest.fixture
def app_and_holder(modules):
    app = create_api()
    holder = app.dependency_overrides[get_project_holder]()
    holder.load(modules)
    return app, holder


@pytest.fixture
def client(app_and_holder):
    return TestClient(app_and_holder[0], client=LOOPBACK_CLIENT)


@pytest.fixture
def holder(app_and_holder):
    return app_and_holder[1]


def _wait_for_run(client, timeout=5.0) -> str:
    deadline = time.monotonic() + timeout
    state = "running"
    while time.monotonic() < deadline:
        state = client.get("/run/status").json()["state"]
        if state != "running":
            break
        time.sleep(0.05)
    return state


def test_state_needs_a_loaded_project():
    client = TestClient(create_api(), client=LOOPBACK_CLIENT)
    assert client.get("/platform/state").status_code == 503
    assert client.get("/platform/stream").status_code == 503


def test_state_hides_device_states_until_monitoring_is_started(client, holder):
    body = client.get("/platform/state").json()
    assert body["live"] is False
    assert body["devices"] == {} and body["displays"] == {}

    holder.monitoring_store.try_manual_start()
    body = client.get("/platform/state").json()
    assert body["live"] is True
    assert {name: d["status"] for name, d in body["devices"].items()} == {
        "pump": "unknown",
        "sensor": "unknown",
    }


def test_a_dry_run_shows_each_command_with_its_run_and_node(client, holder):
    holder.monitoring_store.try_manual_start()

    r = client.post("/run/", json={"protocol": "dose_001.json", "dry_run": True})
    assert r.status_code == 202
    run_id = r.json()["run_id"]
    assert _wait_for_run(client) == "finished"

    pump = client.get("/platform/state").json()["devices"]["pump"]
    assert pump["status"] == "done"
    command = pump["command"]
    assert command["name"] == "infuse"
    assert command["params"] == {"volume": "1 ml"}
    assert (command["run"], command["node"]) == (run_id, "start")


def test_a_command_from_the_device_panel_shows_too(client, holder, mocker):
    mocker.patch.object(BaseClient, "put", return_value=_response())
    mocker.patch.object(BaseClient, "get", return_value=_response(b"true"))
    holder.monitoring_store.try_manual_start()

    r = client.post(
        "/components/commands/pump/withdraw",
        json={"verb": "put", "params": {"volume": "2 ml"}},
    )
    assert r.status_code == 200 and r.json()["ok"] is True

    pump = client.get("/platform/state").json()["devices"]["pump"]
    assert pump["status"] == "done"
    assert pump["command"]["name"] == "withdraw"
    assert pump["command"]["run"] is None


def test_lcds_show_monitoring_readings_from_the_desktop_export(
    tmp_path, modules, client, holder
):
    (tmp_path / "draw").mkdir()
    (tmp_path / "draw" / "platform-live.json").write_text(
        json.dumps(
            {
                "svg_sha256": "",
                "parts": {},
                "displays": {
                    "Pump rate": {
                        "box": [0, 0, 10, 4],
                        "component": "pump",
                        "command": "rate",
                        "kwargs": {},
                    },
                    "Unwatched": {
                        "box": [0, 10, 10, 4],
                        "component": "pump",
                        "command": "volume",
                        "kwargs": {},
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "connectivity" / "monitoring.json").write_text(
        json.dumps(
            {
                "sample_time": 1.0,
                "variables": [{"component": "pump", "command": "rate", "kwargs": {}}],
            }
        ),
        encoding="utf-8",
    )
    holder.load(modules)  # "Refresh project" re-reads the export
    holder.monitoring_store.try_manual_start()

    holder.monitoring_store.record_reading(
        "pump::rate", {"time": "t1", "value": "1.25 ml/min", "error": None}
    )

    displays = client.get("/platform/state").json()["displays"]
    assert displays["Pump rate"] == {
        "value": "1.25 ml/min",
        "at": "t1",
        "error": None,
        "monitored": True,
    }
    assert displays["Unwatched"]["monitored"] is False
    assert displays["Unwatched"]["value"] is None
