"""Through the server: how a run ended is reported, and the first error stops it."""

from __future__ import annotations

import json
import queue
import sqlite3
import textwrap
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from chemunited_sim.cli import server
from chemunited_sim.cli.clock import SimClock
from chemunited_sim.cli.server import SimStatus, SimulationState, app
from chemunited_sim.worker import SimConfig
from chemunited_sim.worker.runner import Worker


def _write_project(project_dir: Path, steps: dict) -> None:
    (project_dir / "draw").mkdir(parents=True)
    (project_dir / "protocols").mkdir()
    (project_dir / "protocols_historic").mkdir()
    (project_dir / "draw" / "setup.py").write_text(
        textwrap.dedent("""
            def build_draw(platform):
                platform.add_component(name="vessel", figure="GlassBottle")
            """),
        encoding="utf-8",
    )
    (project_dir / "protocols" / "__init__.py").write_text(
        textwrap.dedent("""
            from .Work import CustomProcess as WorkProcess, ProcessConfig as WorkConfig
            from .Boom import CustomProcess as BoomProcess, ProcessConfig as BoomConfig

            PROCESSES = {"Work": WorkProcess, "Boom": BoomProcess}
            CONFIGS = {"Work": WorkConfig, "Boom": BoomConfig}
            """),
        encoding="utf-8",
    )
    template = textwrap.dedent("""
        from __future__ import annotations

        import json
        from pathlib import Path

        import networkx as nx
        from pydantic import BaseModel, ConfigDict

        from chemunited_workflow import (
            NodeExecutionContext,
            Process,
            WorkflowEdgeSpec,
            WorkflowNodeSpec,
        )

        ORDER_LOG = Path(__file__).parent.parent / "order.jsonl"


        class ProcessConfig(BaseModel):
            model_config = ConfigDict(frozen=True)

            seconds: float = 0.5


        class CustomProcess(Process[ProcessConfig]):
            def build_workflow(self) -> nx.DiGraph:
                graph = nx.DiGraph()
                for name in ("start", "work"):
                    graph.add_node(
                        name,
                        **WorkflowNodeSpec(node_id=name, method=name).model_dump(
                            exclude_none=True
                        ),
                    )
                graph.add_edge(
                    "start",
                    "work",
                    **WorkflowEdgeSpec(condition=True).model_dump(exclude_none=True),
                )
                return graph

            def start(self, ctx: NodeExecutionContext) -> bool:
                return True

            def work(self, ctx: NodeExecutionContext) -> bool:
                with ORDER_LOG.open("a", encoding="utf-8") as log:
                    log.write(
                        json.dumps([type(self).__module__, self.process_index]) + "\\n"
                    )
                self.platform._wait(self.config.seconds)
                BOOM
                return True
        """)
    (project_dir / "protocols" / "Work.py").write_text(
        template.replace("BOOM", "pass"), encoding="utf-8"
    )
    (project_dir / "protocols" / "Boom.py").write_text(
        template.replace("BOOM", 'raise ValueError("the line is blocked")'),
        encoding="utf-8",
    )
    (project_dir / "protocols_historic" / "protocol.json").write_text(
        json.dumps(steps), encoding="utf-8"
    )


@pytest.fixture
def client(tmp_path):
    server._state = SimulationState(
        sim_status=SimStatus.NO_PROJECT,
        current_t=0.0,
        config=SimConfig(),
        db_path=None,
        project=None,
        clock=SimClock(),
        cmd_queue=queue.Queue(),
        db_dir=tmp_path / "db",
    )
    with TestClient(app) as test_client:
        yield test_client
        server._state._stop_event.set()
        for thread in (server._state._workflow_thread, server._state._worker_thread):
            if thread is not None:
                thread.join(timeout=10.0)
        server._state.sim_status = SimStatus.IDLE


def _start(client, project_dir: Path, **options) -> None:
    response = client.post("/project/load", json={"path": str(project_dir)})
    assert response.status_code == 200
    response = client.post(
        "/simulation/start",
        json={
            "execution_id": "run",
            "dt": 0.1,
            "real_time": False,
            "historical_file": "protocol.json",
            **options,
        },
    )
    assert response.status_code == 200


def _wait_until_idle(client, timeout: float = 20.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = client.get("/status").json()
        if status["sim_status"] == "idle":
            return status
        time.sleep(0.02)
    raise AssertionError("the run didn't end")


def _ran(project_dir: Path) -> list[list]:
    log = project_dir / "order.jsonl"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def _names(ran: list[list]) -> list[tuple[str, int]]:
    return [(module.rsplit(".", 1)[-1], index) for module, index in ran]


def test_finished_run_reports_finished(client, tmp_path) -> None:
    project = tmp_path / "project"
    _write_project(project, {"main_parameter": {}, "Work_3": {}, "Work_1": {}})

    _start(client, project)
    status = _wait_until_idle(client)

    assert status["last_run"] == {
        "outcome": "finished",
        "error": None,
        "process": None,
        "node": None,
    }
    # In key order, each with the index from its key.
    assert _names(_ran(project)) == [("Work", 3), ("Work", 1)]
    assert status["current_t"] == pytest.approx(1.0, abs=0.11)


def test_failed_run_stops_and_reports_where(client, tmp_path) -> None:
    project = tmp_path / "project"
    _write_project(
        project,
        {"main_parameter": {}, "Work_0": {}, "Boom_1": {}, "Work_2": {}},
    )

    _start(client, project)
    status = _wait_until_idle(client)

    last_run = status["last_run"]
    assert last_run["outcome"] == "failed"
    assert last_run["process"] == "Boom_1"
    assert last_run["node"] == "work"
    assert "the line is blocked" in last_run["error"]
    assert _names(_ran(project)) == [("Work", 0), ("Boom", 1)]


def test_error_resilient_run_carries_on(client, tmp_path) -> None:
    project = tmp_path / "project"
    _write_project(project, {"Boom_0": {}, "Work_1": {}})

    _start(client, project, error_resilient=True)
    status = _wait_until_idle(client)

    assert status["last_run"]["outcome"] == "finished"
    assert "the line is blocked" in status["last_run"]["error"]
    assert _names(_ran(project)) == [("Boom", 0), ("Work", 1)]


def test_unknown_process_fails_the_run(client, tmp_path) -> None:
    project = tmp_path / "project"
    _write_project(project, {"Work_0": {}, "Missing_1": {}, "Work_2": {}})

    _start(client, project)
    status = _wait_until_idle(client)

    assert status["last_run"]["outcome"] == "failed"
    assert status["last_run"]["process"] == "Missing_1"
    assert _names(_ran(project)) == [("Work", 0)]


def test_a_crash_in_physics_ends_the_run_and_wakes_the_workflow(
    client, tmp_path, monkeypatch
) -> None:
    project = tmp_path / "project"
    _write_project(project, {"Work_0": {"seconds": 1000.0}})

    def broken(self) -> None:
        raise RuntimeError("the solver blew up")

    monkeypatch.setattr(Worker, "step", broken)
    _start(client, project)
    status = _wait_until_idle(client)

    assert status["last_run"]["outcome"] == "failed"
    assert "the solver blew up" in status["last_run"]["error"]
    assert not server._state._workflow_thread.is_alive()


def test_stopping_a_run_reports_stopped(client, tmp_path) -> None:
    project = tmp_path / "project"
    _write_project(project, {"Work_0": {"seconds": 100000.0}, "Work_1": {}})

    _start(client, project)
    time.sleep(0.2)
    assert client.get("/status").json()["last_run"] is None
    assert client.post("/simulation/stop").status_code == 200
    server._state._workflow_thread.join(timeout=10.0)
    status = client.get("/status").json()

    assert status["last_run"]["outcome"] == "stopped"
    assert status["last_run"]["process"] == "Work_0"
    assert _names(_ran(project)) == [("Work", 0)]


def test_reaching_t_end_stops_a_waiting_workflow(client, tmp_path) -> None:
    project = tmp_path / "project"
    _write_project(project, {"Work_0": {"seconds": 100000.0}})

    _start(client, project, t_end=1.0)
    status = _wait_until_idle(client)

    assert status["last_run"]["outcome"] == "stopped"
    assert status["current_t"] == pytest.approx(1.0, abs=0.11)
    assert not server._state._workflow_thread.is_alive()


def test_recording_options_reach_the_recorder(client, tmp_path) -> None:
    project = tmp_path / "project"
    _write_project(project, {"Work_0": {"seconds": 1.0}})

    _start(client, project, record_interval=0.5, record_cells=False)
    _wait_until_idle(client)

    db = tmp_path / "db" / "run.db"
    with sqlite3.connect(db) as conn:
        meta = dict(conn.execute("SELECT key, value FROM meta"))
        cells = conn.execute("SELECT COUNT(*) FROM edge_cells").fetchone()[0]
    assert meta["record_interval"] == "0.5"
    assert meta["record_cells"] == "False"
    assert meta["skip_unchanged"] == "True"
    assert cells == 0


def test_an_invalid_record_interval_is_refused(client, tmp_path) -> None:
    project = tmp_path / "project"
    _write_project(project, {"Work_0": {}})
    client.post("/project/load", json={"path": str(project)})

    response = client.post(
        "/simulation/start",
        json={"execution_id": "run", "record_interval": 0.0},
    )

    assert response.status_code == 422


def test_real_time_run_reports_stopped(client, tmp_path) -> None:
    project = tmp_path / "project"
    _write_project(project, {"Work_0": {}})
    client.post("/project/load", json={"path": str(project)})
    response = client.post(
        "/simulation/start",
        json={"execution_id": "live", "dt": 0.05, "real_time": True},
    )
    assert response.status_code == 200
    time.sleep(0.15)

    assert client.post("/simulation/stop").status_code == 200
    server._state._worker_thread.join(timeout=10.0)

    assert client.get("/status").json()["last_run"]["outcome"] == "stopped"
