"""Flow-platform temperature and transport-fill regressions."""

from __future__ import annotations

import json
import queue
import re
import shutil
import sqlite3
import time
from pathlib import Path

import pytest
from chemunited_core.common.enums import PhaseKind
from chemunited_core.components.enums import InternalEdgeRole, PortAccess
from fastapi.testclient import TestClient
from loguru import logger

from chemunited_sim.cli import server
from chemunited_sim.cli.clock import SimClock
from chemunited_sim.cli.loader import load_project
from chemunited_sim.cli.server import SimStatus, SimulationState, app
from chemunited_sim.hydraulics.models import HydraulicState
from chemunited_sim.inventory.engine import assimilate, emit_from_sources
from chemunited_sim.inventory.initialiser import build_inventory_states
from chemunited_sim.inventory.port_map import build_port_map
from chemunited_sim.inventory.source_map import build_source_map
from chemunited_sim.transport.models import Pocket
from chemunited_sim.worker import SimConfig, Worker

PROJECT_PATH = Path("tests") / "flow_platform"


@pytest.fixture
def workspace_tmp(request) -> Path:
    safe_name = request.node.name.replace("/", "_").replace("\\", "_")
    path = Path("examples") / "simulation" / "test_flow_platform_tmp" / safe_name
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)
    yield path
    shutil.rmtree(path, ignore_errors=True)


def _stop_background_threads() -> None:
    if server._state is None:
        return
    server._state._stop_event.set()
    for thread in (server._state._workflow_thread, server._state._worker_thread):
        if thread is not None:
            thread.join(timeout=5.0)
    server._state.sim_status = SimStatus.IDLE


def _wait_until_idle(client: TestClient, timeout: float = 40.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if client.get("/status").json()["sim_status"] == "idle":
            return True
        time.sleep(0.05)
    return False


def _dashboard_payload(html_text: str) -> dict:
    match = re.search(
        r'<script id="dashboard-data" type="application/json">(.*?)</script>',
        html_text,
        re.DOTALL,
    )
    assert match is not None
    return json.loads(match.group(1))


def test_reactor_liquid_path_uses_bottom_ports():
    project = load_project(PROJECT_PATH)
    port_map = build_port_map(project.graph, list(project.components.values()))
    source_map = build_source_map(project.graph, list(project.components.values()))

    assert port_map["reactortube_2_reactor_2"].access == PortAccess.BOTTOM
    assert port_map["reactor_3_bpr_1"].access == PortAccess.BOTTOM
    assert "liquidpump_1_tmixer_2" not in port_map
    assert "liquidpump_1_tmixer_2" in source_map


def test_liquidpump_source_emits_from_runtime_inventory():
    project = load_project(PROJECT_PATH)
    states = build_inventory_states(project.graph)
    source_map = build_source_map(project.graph, list(project.components.values()))
    state = states["liquidpump.Inventory"]
    initial_volume = state.liq_volume
    initial_solvent = state.liq_species_moles["solvent"]

    emitted = emit_from_sources(
        source_map,
        project.graph,
        HydraulicState(
            pressures={"liquidpump.1": 101_325.0},
            flows={"liquidpump_1_tmixer_2": 1.0e-8},
        ),
        states,
        dt=0.5,
    )

    pocket = emitted["liquidpump_1_tmixer_2"]
    assert pocket.phase_kind == PhaseKind.LIQUID
    assert pocket.volume == pytest.approx(5.0e-9)
    assert pocket.species_moles["reagent_a"] > 0.0
    assert pocket.species_moles["solvent"] > 0.0
    assert state.liq_volume == pytest.approx(initial_volume - 5.0e-9)
    assert state.liq_species_moles["solvent"] < initial_solvent


def test_liquidpump_source_uses_carrier_only_after_runtime_inventory_runs_dry():
    project = load_project(PROJECT_PATH)
    states = build_inventory_states(project.graph)
    source_map = build_source_map(project.graph, list(project.components.values()))
    state = states["liquidpump.Inventory"]
    state.liq_volume = 2.0e-9
    state.liq_species_moles = {"solvent": 3.0}
    messages = []
    handler_id = logger.add(
        lambda message: messages.append(str(message)),
        level="WARNING",
        format="{message}",
    )

    try:
        emitted = emit_from_sources(
            source_map,
            project.graph,
            HydraulicState(
                pressures={"liquidpump.1": 101_325.0},
                flows={"liquidpump_1_tmixer_2": 1.0e-8},
            ),
            states,
            dt=0.5,
        )
    finally:
        logger.remove(handler_id)

    pocket = emitted["liquidpump_1_tmixer_2"]
    assert pocket.phase_kind == PhaseKind.LIQUID
    assert pocket.volume == pytest.approx(5.0e-9)
    assert pocket.species_moles == {"solvent": pytest.approx(3.0)}
    assert state.liq_volume == pytest.approx(0.0)
    assert any("SyringePump 'liquidpump' ran dry" in message for message in messages)


def test_liquidpump_source_falls_back_to_gas_when_liquid_alone_is_insufficient():
    """Regression test for the stranded-gas-phase bug: an air-gap syringe
    (liquid partially drawn down, real gas headspace already present in the
    same barrel) must draw the full requested dV from the gas phase that is
    genuinely available -- not synthesize carrier air while stranding real
    gas content, and not warn "ran dry" when a real fallback phase exists.
    """
    project = load_project(PROJECT_PATH)
    states = build_inventory_states(project.graph)
    source_map = build_source_map(project.graph, list(project.components.values()))
    state = states["liquidpump.Inventory"]
    # Air-gap scenario: liquid alone can't cover dV, but gas headspace can.
    state.liq_volume = 2.0e-9
    state.liq_species_moles = {"solvent": 3.0}
    state.gas_volume = 1.0e-8
    state.gas_species_moles = {"nitrogen": 4.0}
    messages = []
    handler_id = logger.add(
        lambda message: messages.append(str(message)),
        level="WARNING",
        format="{message}",
    )

    try:
        emitted = emit_from_sources(
            source_map,
            project.graph,
            HydraulicState(
                pressures={"liquidpump.1": 101_325.0},
                flows={"liquidpump_1_tmixer_2": 1.0e-8},
            ),
            states,
            dt=0.5,
        )
    finally:
        logger.remove(handler_id)

    pocket = emitted["liquidpump_1_tmixer_2"]  # dV = 1e-8 * 0.5 = 5e-9 m^3
    assert pocket.phase_kind == PhaseKind.GAS
    assert pocket.volume == pytest.approx(5.0e-9)
    assert pocket.species_moles == {"nitrogen": pytest.approx(2.0)}
    assert "air" not in pocket.species_moles
    assert state.liq_volume == pytest.approx(2.0e-9)  # untouched this tick
    assert state.gas_volume == pytest.approx(5.0e-9)
    assert not any("SyringePump 'liquidpump' ran dry" in m for m in messages)


def test_liquidpump_withdraw_assimilates_into_runtime_inventory():
    project = load_project(PROJECT_PATH)
    states = build_inventory_states(project.graph)
    source_map = build_source_map(project.graph, list(project.components.values()))
    state = states["liquidpump.Inventory"]
    initial_volume = state.liq_volume

    emitted = emit_from_sources(
        source_map,
        project.graph,
        HydraulicState(
            pressures={"liquidpump.1": 101_325.0},
            flows={"liquidpump_1_tmixer_2": -1.0e-8},
        ),
        states,
        dt=0.5,
    )
    assimilate(
        states,
        {
            "liquidpump.Inventory": [
                Pocket(
                    phase_kind=PhaseKind.LIQUID,
                    volume=5.0e-9,
                    species_moles={"product_b": 2.0e-6},
                    temperature=310.0,
                    pressure=101_325.0,
                )
            ]
        },
        HydraulicState(
            pressures={"liquidpump.Inventory": 101_325.0},
            flows={},
        ),
        variable_volume_inventory_ids={"liquidpump.Inventory"},
    )

    assert emitted == {}
    assert state.liq_volume == pytest.approx(initial_volume + 5.0e-9)
    assert state.liq_species_moles["product_b"] == pytest.approx(2.0e-6)


def test_worker_initialises_liquidpump_inventory_from_actual_syringe_volume():
    project = load_project(PROJECT_PATH)
    worker = Worker(project.graph, list(project.components.values()), SimConfig())
    state = worker.inv_states["liquidpump.Inventory"]
    comp = project.components["liquidpump"]
    template = project.graph.inventory_nodes["liquidpump.Inventory"].liq_content
    actual_volume = comp.syringe_actual_volume.to_base_units().magnitude

    assert state.capacity == pytest.approx(
        comp.syringe_volume.to_base_units().magnitude
    )
    assert state.liq_volume == pytest.approx(actual_volume)
    assert state.gas_volume == pytest.approx(0.0)
    assert state.liq_species_moles["solvent"] == pytest.approx(
        template.initial_species["solvent"] / template.volume * actual_volume
    )


def test_mode1_latest_snapshot_keeps_all_transport_edges(workspace_tmp):
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

    messages = []
    handler_id = logger.add(
        lambda message: messages.append(str(message)),
        level="WARNING",
        format="{message}",
    )

    try:
        with TestClient(app) as client:
            resp = client.post(
                "/project/load", json={"path": str(PROJECT_PATH.resolve())}
            )
            assert resp.status_code == 200
            resp = client.post(
                "/simulation/start",
                json={
                    "execution_id": "flow_viz_run",
                    "dt": 0.5,
                    "t_end": None,
                    "real_time": False,
                    "historical_file": "run_001.json",
                },
            )
            assert resp.status_code == 200
            assert _wait_until_idle(client)
            resp = client.get("/simulation/visualization")
            assert resp.status_code == 200
            graph_html = Path(resp.json()["graph_html"])
            dashboard_html = Path(resp.json()["dashboard_html"])
            assert graph_html.exists()
            assert dashboard_html.exists()
            graph_text = graph_html.read_text(encoding="utf-8")
            dashboard_text = dashboard_html.read_text(encoding="utf-8")
            dashboard_payload = _dashboard_payload(dashboard_text)

        assert server._state is not None
        assert server._state.project is not None
        assert server._state.db_path is not None
        expected_transport_edges = {
            edge_id
            for edge_id, edge in server._state.project.graph.edges.items()
            if edge.role == InternalEdgeRole.TRANSPORT
        }

        with sqlite3.connect(server._state.db_path) as conn:
            latest = conn.execute("SELECT MAX(time) FROM node_pressure").fetchone()[0]
            latest_cell_edges = {
                row[0]
                for row in conn.execute(
                    "SELECT DISTINCT edge_id FROM cell_state WHERE time = ?",
                    (latest,),
                )
            }
            average_temperatures = dict(
                conn.execute(
                    """
                    SELECT edge_id, AVG(temperature)
                    FROM cell_state
                    WHERE time = ?
                    GROUP BY edge_id
                    """,
                    (latest,),
                )
            )
            liquidrecicly_volumes = dict(
                conn.execute(
                    """
                    SELECT phase, MAX(volume)
                    FROM inventory_content
                    WHERE time = ? AND node_id = 'liquidrecicly.Inventory'
                    GROUP BY phase
                    """,
                    (latest,),
                )
            )

        assert latest_cell_edges == expected_transport_edges
        assert sum(liquidrecicly_volumes.values()) == pytest.approx(10.0e-6)
        component_ids = {
            component["id"] for component in dashboard_payload["components"]
        }
        edge_ids = {edge["id"] for edge in dashboard_payload["edges"]}
        assert {"reactor", "bpr"} <= component_ids
        assert {"reactor_3_bpr_1", "bpr_2_divertvalve_0"} <= edge_ids
        for edge_id in (
            "reactor_3_bpr_1",
            "bpr_2_divertvalve_0",
            "divertvalve_2_wastesink_1",
        ):
            assert average_temperatures[edge_id] > 298.15
            assert edge_id in graph_text
            edge_payload = next(
                edge for edge in dashboard_payload["edges"] if edge["id"] == edge_id
            )
            signal_titles = {group["title"] for group in edge_payload["signals"]}
            assert {
                "Flow rate",
                "Average cell temperature",
                "Average cell content",
            } <= signal_titles
            content_group = next(
                group
                for group in edge_payload["signals"]
                if group["title"] == "Average cell content"
            )
            trace_names = {trace["name"] for trace in content_group["traces"]}
            # Finite pump calls now complete before the later MFC command starts,
            # so the latest downstream cells may have been flushed back to gas.
            assert trace_names
        assert "average cell temperature" in graph_text
        assert "component-explorer" in dashboard_text
        assert "edge-explorer" in dashboard_text
        assert not any(
            "liquidpump.Inventory" in message and "carrier" in message
            for message in messages
        )
        assert not any(
            "liquidrecicly.Inventory" in message and "carrier" in message
            for message in messages
        )
    finally:
        logger.remove(handler_id)
        _stop_background_threads()
