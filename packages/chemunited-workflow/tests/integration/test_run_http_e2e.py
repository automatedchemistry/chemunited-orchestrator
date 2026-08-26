"""End-to-end HTTP integration tests using a live uvicorn server.

Two executions of run_complex.json (dry_run=True):
  Run A — exercises /run/status and /run/report.
  Run B — exercises /run/stream and /run/report.

Heartbeat timing is not asserted here; tests/unit/test_runner_stream.py owns that.
"""

from __future__ import annotations

import importlib.util
import json
import socket
import sys
import threading
import time
from pathlib import Path

import pytest
import requests as _requests
import uvicorn

from chemunited_workflow.api import create_api
from tests.helpers import make_project_tree

# ── Process sources ───────────────────────────────────────────────────────────

BRANCHING_PROCESS_SRC = """\
from pydantic import BaseModel
from chemunited_workflow import Process, NodeExecutionContext, WorkflowEdgeSpec, WorkflowNodeSpec
import networkx as nx


class BranchingConfig(BaseModel):
    value: float = 1.0


class BranchingProcess(Process):
    def build_workflow(self):
        g = nx.DiGraph()
        for nid, method, label in [
            ("start",        "start_node",        "Start"),
            ("condition",    "condition_node",     "Condition"),
            ("parallel_a",   "parallel_a_node",   "Parallel A"),
            ("parallel_b",   "parallel_b_node",   "Parallel B"),
            ("false_branch", "false_branch_node", "False Branch"),
            ("join",         "join_node",          "Join"),
        ]:
            g.add_node(
                nid,
                **WorkflowNodeSpec(node_id=nid, method=method, label=label).model_dump(
                    exclude_none=True
                ),
            )
        g.add_edge("start",      "condition",    **WorkflowEdgeSpec(condition=True).model_dump(exclude_none=True))
        g.add_edge("condition",  "parallel_a",   **WorkflowEdgeSpec(condition=True).model_dump(exclude_none=True))
        g.add_edge("condition",  "parallel_b",   **WorkflowEdgeSpec(condition=True).model_dump(exclude_none=True))
        g.add_edge("condition",  "false_branch", **WorkflowEdgeSpec(condition=False).model_dump(exclude_none=True))
        g.add_edge("parallel_a", "join",         **WorkflowEdgeSpec(condition=True).model_dump(exclude_none=True))
        g.add_edge("parallel_b", "join",         **WorkflowEdgeSpec(condition=True).model_dump(exclude_none=True))
        return g

    def start_node(self, ctx: NodeExecutionContext) -> bool:
        return True

    def condition_node(self, ctx: NodeExecutionContext) -> bool:
        return True

    def parallel_a_node(self, ctx: NodeExecutionContext) -> bool:
        return True

    def parallel_b_node(self, ctx: NodeExecutionContext) -> bool:
        return True

    def false_branch_node(self, ctx: NodeExecutionContext) -> bool:
        return True

    def join_node(self, ctx: NodeExecutionContext) -> bool:
        return True
"""

LOOP_PROCESS_SRC = """\
import time
from pydantic import BaseModel
from chemunited_workflow import Process, NodeExecutionContext, WorkflowEdgeSpec, WorkflowNodeSpec
import networkx as nx


class LoopConfig(BaseModel):
    max_loops: int = 3


class LoopProcess(Process):
    def build_workflow(self):
        g = nx.DiGraph()
        for nid, method, label in [
            ("start",         "start_node",         "Start"),
            ("loop_script",   "loop_script_node",   "Loop Script"),
            ("loop_decision", "loop_decision_node", "Loop Decision"),
            ("finish",        "finish_node",        "Finish"),
        ]:
            g.add_node(
                nid,
                **WorkflowNodeSpec(node_id=nid, method=method, label=label).model_dump(
                    exclude_none=True
                ),
            )
        g.add_edge("start",         "loop_script",   **WorkflowEdgeSpec(condition=True).model_dump(exclude_none=True))
        g.add_edge("loop_script",   "loop_decision", **WorkflowEdgeSpec(condition=True).model_dump(exclude_none=True))
        # Loopback: loop_decision returns True (iterations 0-2) -> loop back to loop_script
        g.add_edge("loop_decision", "loop_script", loopback=True, trigger_on=True, max_iterations=4)
        # Normal exit: loop_decision returns False (iteration 3) -> finish
        g.add_edge("loop_decision", "finish", **WorkflowEdgeSpec(condition=False).model_dump(exclude_none=True))
        return g

    def start_node(self, ctx: NodeExecutionContext) -> bool:
        return True

    def loop_script_node(self, ctx: NodeExecutionContext) -> bool:
        return True

    def loop_decision_node(self, ctx: NodeExecutionContext) -> bool:
        # Pause long enough for the SSE stream to poll and capture events across
        # multiple 100 ms intervals; 4 calls × 150 ms = 600 ms total workflow time.
        time.sleep(0.15)
        # True for iterations 0, 1, 2 (triggers loopback); False for iteration 3 (exits)
        return ctx.iteration < 3

    def finish_node(self, ctx: NodeExecutionContext) -> bool:
        return True
"""

_RUN_TIMEOUT = 15.0


# ── Helpers ───────────────────────────────────────────────────────────────────


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Register in sys.modules so inspect.getfile() resolves the class source path,
    # which load_parameters() needs to locate protocols_historic/ at runtime.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _poll_until_finished(
    base_url: str, timeout: float = _RUN_TIMEOUT
) -> tuple[str, list[dict]]:
    """Poll /status until terminal state. Returns (state, all_events_seen)."""
    deadline = time.time() + timeout
    all_events: list[dict] = []
    state = "running"
    while time.time() < deadline:
        resp = _requests.get(f"{base_url}/run/status", timeout=5.0)
        assert resp.status_code == 200
        body = resp.json()
        all_events.extend(body.get("events", []))
        state = body["state"]
        if state in ("finished", "failed", "cancelled"):
            break
        time.sleep(0.05)
    return state, all_events


def _node_state_completed(node_state: dict, key: str) -> bool:
    return "COMPLETED" in node_state.get(key, "")


def _node_state_inactive(node_state: dict, key: str) -> bool:
    return "INACTIVE" in node_state.get(key, "")


# ── Module-scoped fixtures ────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("e2e_http")
    dirs = make_project_tree(tmp_path)

    (dirs["connectivity_dir"] / "associations.json").write_text(
        json.dumps(
            {
                "server_url": "http://127.0.0.1:19999",
                "associations": [
                    {"component": "device_a", "component_url": "api/device_a"}
                ],
            }
        ),
        encoding="utf-8",
    )

    (dirs["process_dir"] / "branching_process.py").write_text(
        BRANCHING_PROCESS_SRC, encoding="utf-8"
    )
    (dirs["process_dir"] / "loop_process.py").write_text(
        LOOP_PROCESS_SRC, encoding="utf-8"
    )

    snapshot = {
        "main_parameter": {"reagent_volume_ml": 5.0, "target_temperature_c": 25.0},
        "branching_process_0": {"value": 1.0},
        "loop_process_1": {"max_loops": 3},
    }
    (dirs["historic_dir"] / "run_complex.json").write_text(
        json.dumps(snapshot), encoding="utf-8"
    )

    return {"dirs": dirs, "tmp_path": tmp_path}


@pytest.fixture(scope="module")
def app_e2e(project):
    dirs = project["dirs"]
    branch_mod = _load_module(
        dirs["process_dir"] / "branching_process.py", "branching_process"
    )
    loop_mod = _load_module(dirs["process_dir"] / "loop_process.py", "loop_process")
    main_mod = _load_module(
        dirs["process_dir"] / "main_parameters.py", "main_parameters"
    )

    from chemunited_workflow.api.dependencies import get_project_holder
    from chemunited_workflow.project_loader import ProjectModules

    api = create_api()
    holder = api.dependency_overrides[get_project_holder]()
    holder.load(
        ProjectModules(
            project_dir=project["tmp_path"],
            processes={
                "branching_process": branch_mod.BranchingProcess,
                "loop_process": loop_mod.LoopProcess,
            },
            configs={
                "branching_process": branch_mod.BranchingConfig,
                "loop_process": loop_mod.LoopConfig,
            },
            main_parameter_class=main_mod.MainParameter,
        )
    )
    return api


@pytest.fixture(scope="module")
def live_server(app_e2e):
    """Start a real uvicorn server on an OS-assigned localhost port."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]

    config = uvicorn.Config(app_e2e, host="127.0.0.1", port=0, log_level="warning")
    server = uvicorn.Server(config)

    thread = threading.Thread(
        target=server.run, kwargs={"sockets": [sock]}, daemon=True
    )
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 10.0
    started = False
    while time.time() < deadline:
        try:
            r = _requests.get(f"{base_url}/run/pool", timeout=0.5)
            if r.status_code == 200:
                started = True
                break
        except Exception:
            time.sleep(0.05)

    if not started:
        server.should_exit = True
        thread.join(timeout=5.0)
        try:
            sock.close()
        except OSError:
            pass
        pytest.fail("Live uvicorn server did not become reachable within 10 s")

    yield base_url

    server.should_exit = True
    thread.join(timeout=5.0)
    try:
        sock.close()
    except OSError:
        pass


# ── Run A: /status + /report ──────────────────────────────────────────────────


def test_run_a_status_poll_and_report(live_server):
    base_url = live_server

    r = _requests.post(
        f"{base_url}/run/",
        json={"protocol": "run_complex.json", "dry_run": True},
        timeout=5.0,
    )
    assert r.status_code == 202

    state, events = _poll_until_finished(base_url)
    assert state == "finished", f"Run did not finish: state={state!r}"
    assert len(events) > 0, "Expected at least one event from status polling"

    report_r = _requests.get(f"{base_url}/run/report", timeout=5.0)
    assert report_r.status_code == 200
    report = report_r.json()
    assert report["state"] == "finished"
    assert (
        len(report["results"]) == 2
    ), f"Expected 2 process results, got {len(report['results'])}"

    # --- Process 0: branching workflow ---
    branch_ns = report["results"][0]["node_state"]
    for key in ("start:0", "condition:0", "parallel_a:0", "parallel_b:0", "join:0"):
        assert _node_state_completed(
            branch_ns, key
        ), f"{key!r} should be COMPLETED; got {branch_ns.get(key)!r}"
    assert _node_state_inactive(
        branch_ns, "false_branch:0"
    ), f"false_branch:0 should be INACTIVE; got {branch_ns.get('false_branch:0')!r}"

    # --- Process 1: loop workflow ---
    loop_result = report["results"][1]
    loop_ns = loop_result["node_state"]
    loop_nr = loop_result["node_result"]

    for i in range(4):
        key = f"loop_script:{i}"
        assert _node_state_completed(
            loop_ns, key
        ), f"{key!r} should be COMPLETED; got {loop_ns.get(key)!r}"

    for i in range(3):
        key = f"loop_decision:{i}"
        assert _node_state_completed(
            loop_ns, key
        ), f"{key!r} should be COMPLETED; got {loop_ns.get(key)!r}"
        assert (
            loop_nr.get(key) is True
        ), f"{key!r} should have result=True; got {loop_nr.get(key)!r}"

    assert _node_state_completed(
        loop_ns, "loop_decision:3"
    ), f"loop_decision:3 should be COMPLETED; got {loop_ns.get('loop_decision:3')!r}"
    assert (
        loop_nr.get("loop_decision:3") is False
    ), f"loop_decision:3 should have result=False; got {loop_nr.get('loop_decision:3')!r}"

    assert _node_state_completed(
        loop_ns, "finish:3"
    ), f"finish:3 should be COMPLETED; got {loop_ns.get('finish:3')!r}"


# ── Run B: /stream + /report ──────────────────────────────────────────────────


def test_run_b_stream_and_report(live_server):
    base_url = live_server

    r = _requests.post(
        f"{base_url}/run/",
        json={"protocol": "run_complex.json", "dry_run": True},
        timeout=5.0,
    )
    assert r.status_code == 202

    node_events: list[dict] = []
    final_state: str | None = None

    with _requests.get(
        f"{base_url}/run/stream", stream=True, timeout=_RUN_TIMEOUT
    ) as resp:
        assert resp.status_code == 200
        for raw_line in resp.iter_lines(decode_unicode=True):
            if not raw_line or not raw_line.startswith("data: "):
                continue
            payload = json.loads(raw_line[6:])
            if "state" in payload and "event_type" not in payload:
                final_state = payload["state"]
                break
            node_events.append(payload)

    assert (
        final_state == "finished"
    ), f"Stream final frame should carry state=finished; got {final_state!r}"
    assert len(node_events) > 0, "Expected workflow events in the SSE stream"

    event_types = {e.get("event_type") for e in node_events}
    assert (
        "EXECUTION_STARTED" in event_types
    ), f"EXECUTION_STARTED missing from stream events: {event_types}"
    assert (
        "NODE_COMPLETED" in event_types
    ), f"NODE_COMPLETED missing from stream events: {event_types}"

    loopback_events = [
        e for e in node_events if e.get("event_type") == "LOOPBACK_TRIGGERED"
    ]
    assert (
        len(loopback_events) == 3
    ), f"Expected 3 LOOPBACK_TRIGGERED events (iterations 0-2); got {len(loopback_events)}"

    report_r = _requests.get(f"{base_url}/run/report", timeout=5.0)
    assert report_r.status_code == 200
    report = report_r.json()
    assert report["state"] == "finished"
    assert len(report["results"]) == 2
