"""Tests for the chemunited-sim MCP tool layer.

Tools are called directly against a `FastMCP` instance via
`asyncio.run(mcp_server.call_tool(name, args))` — no HTTP/stdio transport is
needed, mirroring chemunited-workflow's `tests/unit/test_mcp.py`. State setup
(`server._state = SimulationState(...)`) mirrors `test_flow_platform.py`,
since MCP tools read/write the same module-level state as the REST API.
"""

from __future__ import annotations

import asyncio
import json
import queue
import shutil
import time
from pathlib import Path

import pytest

from chemunited_sim.cli import server
from chemunited_sim.cli.clock import SimClock
from chemunited_sim.cli.server import SimStatus, SimulationState
from chemunited_sim.mcp import create_mcp_server
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
    path = Path("examples") / "simulation" / "test_mcp_tmp" / safe_name
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def state(workspace_tmp) -> SimulationState:
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
    yield server._state
    _stop_background_threads()


@pytest.fixture
def mcp_server():
    return create_mcp_server()


def _call(mcp_server, name: str, args: dict | None = None) -> dict:
    result = asyncio.run(mcp_server.call_tool(name, args or {}))
    content = result[0] if isinstance(result, tuple) else result
    return json.loads(content[0].text)


@pytest.fixture
def loaded(state, mcp_server) -> SimulationState:
    result = _call(mcp_server, "load_project", {"path": str(PROJECT_PATH.resolve())})
    assert "error" not in result, result
    return state


def _wait_until_idle(mcp_server, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _call(mcp_server, "get_status")["sim_status"] == "idle":
            return True
        time.sleep(0.05)
    return False


def _start_mode2_run(
    mcp_server, execution_id: str = "mcp_run", dt: float = 0.5, t_end: float = 2.0
) -> dict:
    result = _call(
        mcp_server,
        "start_simulation",
        {"execution_id": execution_id, "dt": dt, "t_end": t_end, "real_time": True},
    )
    assert "error" not in result, result
    return result


# ---------------------------------------------------------------------------
# 1 — Server factory
# ---------------------------------------------------------------------------


def test_create_mcp_server_configures_http_transport_settings():
    mcp_server = create_mcp_server(
        host="0.0.0.0", port=1999, streamable_http_path="/custom-mcp"
    )
    assert mcp_server.settings.host == "0.0.0.0"
    assert mcp_server.settings.port == 1999
    assert mcp_server.settings.streamable_http_path == "/custom-mcp"


# ---------------------------------------------------------------------------
# 2 — Project & status
# ---------------------------------------------------------------------------


def test_get_status_initial(state, mcp_server):
    result = _call(mcp_server, "get_status")
    assert result["sim_status"] == "no_project"
    assert result["project_loaded"] is False


def test_get_project_before_load(state, mcp_server):
    result = _call(mcp_server, "get_project")
    assert "error" in result


def test_load_project_success(state, mcp_server):
    result = _call(mcp_server, "load_project", {"path": str(PROJECT_PATH.resolve())})
    assert REQUIRED_COMPONENTS <= set(result["components"])


def test_load_project_bad_path(state, mcp_server):
    result = _call(mcp_server, "load_project", {"path": "/nonexistent/path/project"})
    assert "error" in result


def test_get_status_and_project_after_load(loaded, mcp_server):
    status = _call(mcp_server, "get_status")
    assert status["sim_status"] == "idle"
    assert status["project_loaded"] is True

    project = _call(mcp_server, "get_project")
    assert REQUIRED_COMPONENTS <= set(project["components"])
    assert "simulate" in project["processes"]


# ---------------------------------------------------------------------------
# 3 — Run control
# ---------------------------------------------------------------------------


def test_start_without_project(state, mcp_server):
    result = _call(
        mcp_server,
        "start_simulation",
        {"execution_id": "x", "dt": 0.1, "t_end": 1.0, "real_time": False},
    )
    assert "error" in result


def test_stop_when_idle(loaded, mcp_server):
    result = _call(mcp_server, "stop_simulation")
    assert "error" in result


def test_send_component_command_when_idle(loaded, mcp_server):
    result = _call(
        mcp_server,
        "send_component_command",
        {"component": "liquidpump", "command": "pause"},
    )
    assert "error" in result


def test_mode2_start_and_stop(loaded, mcp_server):
    result = _start_mode2_run(mcp_server)
    assert Path(result["db_path"]).exists() or Path(result["db_path"]).parent.exists()
    assert _call(mcp_server, "get_status")["sim_status"] == "running"

    stop_result = _call(mcp_server, "stop_simulation")
    assert "error" not in stop_result
    assert _call(mcp_server, "get_status")["sim_status"] == "idle"


def test_mode1_runs_to_end(loaded, mcp_server):
    result = _call(
        mcp_server,
        "start_simulation",
        {
            "execution_id": "mode1_run",
            "dt": 0.5,
            "real_time": False,
            "historical_file": "run_001.json",
        },
    )
    assert "error" not in result
    assert _wait_until_idle(mcp_server, timeout=30.0), "simulation did not reach idle"


def test_send_component_command_during_mode2(loaded, mcp_server):
    _start_mode2_run(mcp_server)
    result = _call(
        mcp_server,
        "send_component_command",
        {"component": "liquidpump", "command": "pause"},
    )
    assert result.get("queued") is True
    _call(mcp_server, "stop_simulation")


# ---------------------------------------------------------------------------
# 4 — Human-facing outputs
# ---------------------------------------------------------------------------


def test_get_simulation_db_before_run(loaded, mcp_server):
    result = _call(mcp_server, "get_simulation_db")
    assert "error" in result


def test_get_simulation_visualization_after_run(loaded, mcp_server):
    _start_mode2_run(mcp_server)
    assert _wait_until_idle(mcp_server, timeout=10.0)

    result = _call(mcp_server, "get_simulation_visualization")
    assert "error" not in result, result
    dashboard_html = Path(result["dashboard_html"])
    assert dashboard_html.exists()
    assert "reactor" in dashboard_html.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 5 — Results & analysis
# ---------------------------------------------------------------------------


def test_list_result_series_before_run(loaded, mcp_server):
    result = _call(mcp_server, "list_result_series")
    assert "error" in result


def test_get_latest_state_before_run(loaded, mcp_server):
    result = _call(mcp_server, "get_latest_state")
    assert "error" in result


def test_results_after_run(loaded, mcp_server):
    _start_mode2_run(mcp_server)
    assert _wait_until_idle(mcp_server, timeout=10.0)

    series = _call(mcp_server, "list_result_series")
    assert "error" not in series, series
    assert series["nodes"]
    assert series["edges"]
    assert "reactor.Inventory" in series["nodes"]

    latest = _call(mcp_server, "get_latest_state")
    assert "error" not in latest, latest
    assert latest["pressures_bar"]
    assert latest["flows_mlmin"]
    assert "reactor.Inventory" in latest["inventories"]

    node_profile = _call(
        mcp_server, "get_node_profile", {"node_id": "reactor.Inventory"}
    )
    assert "error" not in node_profile, node_profile
    assert node_profile["pressure_bar"]
    assert {"time_s", "value"} <= set(node_profile["pressure_bar"][0])
    assert node_profile["temperature_k"]

    edge_id = series["edges"][0]
    edge_profile = _call(mcp_server, "get_edge_profile", {"edge_id": edge_id})
    assert "error" not in edge_profile, edge_profile
    assert edge_profile["flow_mlmin"]
    assert {"time_s", "value"} <= set(edge_profile["flow_mlmin"][0])

    tailed = _call(
        mcp_server,
        "get_node_profile",
        {"node_id": "reactor.Inventory", "tail": 1},
    )
    assert len(tailed["pressure_bar"]) == 1


def test_get_node_profile_unknown_node(loaded, mcp_server):
    _start_mode2_run(mcp_server)
    assert _wait_until_idle(mcp_server, timeout=10.0)

    result = _call(mcp_server, "get_node_profile", {"node_id": "does-not-exist"})
    assert "error" in result
