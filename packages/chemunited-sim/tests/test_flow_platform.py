"""Integration tests for the flow_platform server project.

Exercises all eight REST endpoints using the flow_platform example project as
a fixture.  Follows the TestClient + server._state pattern established in
test_visualization.py.
"""

from __future__ import annotations

import json
import queue
import shutil
import time
from pathlib import Path

import networkx as nx
import pytest
from chemunited_workflow import (
    NodeExecutionContext,
    Process,
    WorkflowEdgeSpec,
    WorkflowNodeSpec,
)
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict

from chemunited_sim.cli import server
from chemunited_sim.cli.clock import SimClock
from chemunited_sim.cli.server import SimStatus, SimulationState, app
from chemunited_sim.worker import SimConfig

PROJECT_PATH = Path("tests") / "flow_platform"

REQUIRED_COMPONENTS = {
    "liquidpump",
    "reactortube",
    "reactor",
    "bpr",
    "divertvalve",
    "mfc",
}


class _FinitePumpConfig(BaseModel):
    model_config = ConfigDict(frozen=True)


class _FinitePumpProcess(Process[_FinitePumpConfig]):
    def build_workflow(self) -> nx.DiGraph:
        graph = nx.DiGraph()
        for node_id, method in (
            ("start", "start"),
            ("pump", "pump"),
            ("end", "finish"),
        ):
            graph.add_node(
                node_id,
                **WorkflowNodeSpec(node_id=node_id, method=method).model_dump(
                    exclude_none=True
                ),
            )
        graph.add_edge(
            "start",
            "pump",
            **WorkflowEdgeSpec(condition=True).model_dump(exclude_none=True),
        )
        graph.add_edge(
            "pump",
            "end",
            **WorkflowEdgeSpec(condition=True).model_dump(exclude_none=True),
        )
        return graph

    def start(self, _ctx: NodeExecutionContext) -> bool:
        return True

    def pump(self, _ctx: NodeExecutionContext) -> bool:
        self.platform["pump"].put("infuse", rate="1 ml/min", volume="1 ml")
        return True

    def finish(self, _ctx: NodeExecutionContext) -> bool:
        return True


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _stop_background_threads() -> None:
    if server._state is None:
        return
    server._state._stop_event.set()
    for thread in (server._state._workflow_thread, server._state._worker_thread):
        if thread is not None:
            thread.join(timeout=5.0)
    server._state.sim_status = SimStatus.IDLE


@pytest.fixture
def workspace_tmp(request) -> Path:
    safe_name = request.node.name.replace("/", "_").replace("\\", "_")
    path = Path("examples") / "simulation" / "test_full_project_tmp" / safe_name
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def client(workspace_tmp) -> TestClient:
    server._state = SimulationState(
        sim_status=SimStatus.NO_PROJECT,
        current_t=0.0,
        config=SimConfig(),
        db_path=None,
        project=None,
        clock=SimClock(),
        cmd_queue=queue.Queue(),
        db_dir=workspace_tmp,
    )
    with TestClient(app) as test_client:
        yield test_client
        _stop_background_threads()


@pytest.fixture
def loaded_client(client) -> TestClient:
    resp = client.post("/project/load", json={"path": str(PROJECT_PATH.resolve())})
    assert resp.status_code == 200
    return client


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _wait_until_idle(c: TestClient, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if c.get("/status").json()["sim_status"] == "idle":
            return True
        time.sleep(0.05)
    return False


def _start_mode1(c: TestClient, execution_id: str = "test_run") -> None:
    resp = c.post(
        "/simulation/start",
        json={
            "execution_id": execution_id,
            "dt": 0.5,
            "t_end": None,
            "real_time": False,
            "historical_file": "run_001.json",
        },
    )
    assert resp.status_code == 200
    return resp


def _start_mode2(c: TestClient, execution_id: str = "test_run_rt") -> None:
    resp = c.post(
        "/simulation/start",
        json={
            "execution_id": execution_id,
            "dt": 0.1,
            "t_end": None,
            "real_time": True,
        },
    )
    assert resp.status_code == 200
    return resp


# ---------------------------------------------------------------------------
# 1 — Status endpoint
# ---------------------------------------------------------------------------


def test_status_initial(client):
    resp = client.get("/status")
    assert resp.status_code == 200
    assert resp.json()["sim_status"] == "no_project"
    assert resp.json()["project_loaded"] is False


def test_status_after_load(loaded_client):
    resp = loaded_client.get("/status")
    assert resp.status_code == 200
    assert resp.json()["sim_status"] == "idle"
    assert resp.json()["project_loaded"] is True


# ---------------------------------------------------------------------------
# 2 — Project endpoints
# ---------------------------------------------------------------------------


def test_get_project_before_load(client):
    assert client.get("/project").status_code == 404


def test_project_load_succeeds(client):
    resp = client.post("/project/load", json={"path": str(PROJECT_PATH.resolve())})
    assert resp.status_code == 200
    body = resp.json()
    assert REQUIRED_COMPONENTS <= set(body["components"])


def test_project_load_bad_path(client):
    resp = client.post("/project/load", json={"path": "/nonexistent/path/project"})
    assert resp.status_code == 422


def test_project_load_rejected_when_running(loaded_client):
    _start_mode2(loaded_client)
    resp = loaded_client.post(
        "/project/load", json={"path": str(PROJECT_PATH.resolve())}
    )
    assert resp.status_code == 409
    loaded_client.post("/simulation/stop")


def test_get_project_after_load(loaded_client):
    resp = loaded_client.get("/project")
    assert resp.status_code == 200
    body = resp.json()
    assert "components" in body
    assert "processes" in body
    assert REQUIRED_COMPONENTS <= set(body["components"])
    assert "simulate" in body["processes"]


# ---------------------------------------------------------------------------
# 3 — Simulation lifecycle
# ---------------------------------------------------------------------------


def test_start_without_project(client):
    resp = client.post(
        "/simulation/start",
        json={"execution_id": "x", "dt": 0.1, "t_end": 1.0, "real_time": False},
    )
    assert resp.status_code == 409


def test_stop_when_idle(loaded_client):
    assert loaded_client.post("/simulation/stop").status_code == 409


def test_command_when_idle(loaded_client):
    resp = loaded_client.post(
        "/simulation/command",
        json={"component": "liquidpump", "command": "pause", "kwargs": {}},
    )
    assert resp.status_code == 409


def test_db_before_run(loaded_client):
    assert loaded_client.get("/simulation/db").status_code == 404


def test_mode2_start_and_stop(loaded_client):
    resp = _start_mode2(loaded_client)
    db_path = Path(resp.json()["db_path"])
    assert db_path.with_name(f"{db_path.stem}_log.log").exists()
    assert loaded_client.get("/status").json()["sim_status"] == "running"
    resp = loaded_client.post("/simulation/stop")
    assert resp.status_code == 200
    assert loaded_client.get("/status").json()["sim_status"] == "idle"


def test_mode2_double_start_rejected(loaded_client):
    _start_mode2(loaded_client, "run_a")
    resp = loaded_client.post(
        "/simulation/start",
        json={"execution_id": "run_b", "dt": 0.1, "real_time": True},
    )
    assert resp.status_code == 409
    loaded_client.post("/simulation/stop")


def test_mode1_runs_to_end(loaded_client):
    _start_mode1(loaded_client)
    assert _wait_until_idle(
        loaded_client, timeout=30.0
    ), "simulation did not reach idle"
    assert loaded_client.get("/status").json()["sim_status"] == "idle"


def test_mode1_waits_for_inferred_pump_completion(loaded_client, workspace_tmp):
    state = server.get_state()
    assert state.project is not None
    state.project.processes["finite_pump"] = _FinitePumpProcess
    state.project.configs["finite_pump"] = _FinitePumpConfig
    historical_file = workspace_tmp / "finite_pump.json"
    historical_file.write_text(
        json.dumps({"main_parameter": {}, "finite_pump_0": {}}),
        encoding="utf-8",
    )

    resp = loaded_client.post(
        "/simulation/start",
        json={
            "execution_id": "finite_pump",
            "dt": 0.5,
            "t_end": None,
            "real_time": False,
            "historical_file": str(historical_file.resolve()),
        },
    )

    assert resp.status_code == 200
    assert _wait_until_idle(loaded_client, timeout=30.0)
    assert state.current_t >= 60.0
    assert state.project.components["pump"].flow_rate_si == 0.0


def test_simulation_db_after_run(loaded_client):
    _start_mode1(loaded_client, "db_test_run")
    assert _wait_until_idle(loaded_client, timeout=30.0)
    resp = loaded_client.get("/simulation/db")
    assert resp.status_code == 200
    db_path = Path(resp.json()["db_path"])
    assert db_path.exists()
    assert db_path.suffix == ".db"


def test_command_during_mode2(loaded_client):
    _start_mode2(loaded_client)
    resp = loaded_client.post(
        "/simulation/command",
        json={"component": "liquidpump", "command": "pause", "kwargs": {}},
    )
    assert resp.status_code == 200
    assert resp.json()["queued"] is True
    loaded_client.post("/simulation/stop")


# ---------------------------------------------------------------------------
# 4 — Visualization
# ---------------------------------------------------------------------------


def test_visualization_before_load(client):
    assert client.get("/simulation/visualization").status_code == 404


def test_visualization_after_run(loaded_client):
    # Use Mode 2 (real_time=True) so the worker thread actually steps the
    # simulation — Mode 1's async workflow exits immediately in the test
    # runner, producing zero recorded snapshots.
    resp = loaded_client.post(
        "/simulation/start",
        json={"execution_id": "viz_run", "dt": 0.5, "t_end": 2.0, "real_time": True},
    )
    assert resp.status_code == 200
    assert _wait_until_idle(loaded_client, timeout=10.0)
    resp = loaded_client.get("/simulation/visualization")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")
    dashboard_html = Path(resp.json()["dashboard_html"])
    assert dashboard_html.exists()
    assert "reactor" in dashboard_html.read_text(encoding="utf-8")
