"""Tests for pyvis visualization and API endpoint behavior."""

from __future__ import annotations

import json
import queue
import re
import shutil
import sqlite3
from collections import deque
from pathlib import Path
from types import SimpleNamespace

import pytest
from chemunited_core.common.enums import PhaseKind
from chemunited_core.components.enums import InternalEdgeRole
from fastapi.testclient import TestClient

from chemunited_sim.adapter.models import HydraulicEdge, HydraulicGraph, HydraulicNode
from chemunited_sim.cli import server
from chemunited_sim.cli.clock import SimClock
from chemunited_sim.cli.loader import ProjectState
from chemunited_sim.cli.server import SimStatus, SimulationState, app
from chemunited_sim.hydraulics.models import HydraulicState
from chemunited_sim.inventory.models import InventoryState
from chemunited_sim.recorder import Recorder
from chemunited_sim.transport.models import Pocket, TransportState
from chemunited_sim.visualization import (
    EdgeCellSnapshot,
    InventorySnapshot,
    NoSnapshotsError,
    VisualizationSnapshot,
    load_latest_snapshot,
    render_dashboard_html,
    render_pyvis_html,
)
from chemunited_sim.worker import SimConfig


@pytest.fixture
def workspace_tmp(request) -> Path:
    safe_name = request.node.name.replace("/", "_").replace("\\", "_")
    path = Path("examples") / "simulation" / "test_visualization_tmp" / safe_name
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)
    yield path
    shutil.rmtree(path, ignore_errors=True)


def _make_node(node_id: str, component: str = "comp") -> HydraulicNode:
    return HydraulicNode(
        node_id=node_id,
        boundary=None,
        is_hub=False,
        component=component,
    )


def _make_edge(
    edge_id: str,
    origin: str,
    dest: str,
    *,
    flow_component: str = "comp",
) -> HydraulicEdge:
    return HydraulicEdge(
        edge_id=edge_id,
        origin_node_id=origin,
        destination_node_id=dest,
        length=1.0,
        diameter=0.004,
        role=InternalEdgeRole.TRANSPORT,
        resistance_override=None,
        component=flow_component,
        is_external=False,
    )


def _simple_graph() -> HydraulicGraph:
    graph = HydraulicGraph()
    graph.nodes["n0"] = _make_node("n0")
    graph.nodes["n1"] = _make_node("n1")
    graph.edges["e1"] = _make_edge("e1", "n0", "n1")
    return graph


def _transport_state(graph: HydraulicGraph) -> TransportState:
    edge_queues = {}
    for eid, edge in graph.edges.items():
        pocket = Pocket(
            phase_kind=PhaseKind.GAS,
            volume=1.0e-6,
            species_moles={},
            temperature=298.15,
            pressure=101_325.0,
        )
        edge_queues[eid] = deque([pocket])
    return TransportState(edge_queues=edge_queues)


def _inventory_state(node_id: str = "v1.Inventory") -> InventoryState:
    return InventoryState(
        node_id=node_id,
        capacity=1.0e-3,
        pressure=200_000.0,
        temperature=298.15,
        liq_volume=5.0e-4,
        gas_volume=5.0e-4,
        liq_species_moles={"water": 10.0},
        gas_species_moles={},
    )


def _write_recorded_db(db_path: Path, graph: HydraulicGraph) -> None:
    rec = Recorder(db_path=db_path, graph=graph, dt=0.1, record_interval=1.0)
    try:
        rec.record(
            0.0,
            HydraulicState(
                pressures={"n0": 200_000.0, "n1": 101_325.0},
                flows={"e1": 1.0e-6},
            ),
            _transport_state(graph),
            {"v1.Inventory": _inventory_state()},
        )
        rec.record(
            1.0,
            HydraulicState(
                pressures={"n0": 210_000.0, "n1": 101_325.0},
                flows={"e1": -2.0e-6},
            ),
            _transport_state(graph),
            {"v1.Inventory": _inventory_state()},
        )
    finally:
        rec.close()


def _dashboard_payload(html_text: str) -> dict:
    match = re.search(
        r'<script id="dashboard-data" type="application/json">(.*?)</script>',
        html_text,
        re.DOTALL,
    )
    assert match is not None
    return json.loads(match.group(1))


def test_load_latest_snapshot_reads_latest_time(workspace_tmp):
    graph = _simple_graph()
    db_path = workspace_tmp / "run.db"
    _write_recorded_db(db_path, graph)

    snapshot = load_latest_snapshot(db_path)

    assert snapshot.time == pytest.approx(1.0)
    assert snapshot.pressures["n0"] == pytest.approx(210_000.0)
    assert snapshot.flows["e1"] == pytest.approx(-2.0e-6)
    assert snapshot.inventories["v1.Inventory"].species_moles["liquid"]["water"] == (
        pytest.approx(10.0)
    )


def test_load_latest_snapshot_raises_for_db_without_snapshots(workspace_tmp):
    graph = _simple_graph()
    db_path = workspace_tmp / "empty.db"
    rec = Recorder(db_path=db_path, graph=graph, dt=0.1)
    rec.close()

    with pytest.raises(NoSnapshotsError):
        load_latest_snapshot(db_path)


def test_render_pyvis_html_contains_graph_and_reversed_flow():
    graph = _simple_graph()
    snapshot = load_latest_snapshot_from_rows(
        pressures={"n0": 200_000.0, "n1": 101_325.0},
        flows={"e1": -1.0e-6},
    )

    html = render_pyvis_html(
        graph=graph,
        components=[SimpleNamespace(name="comp")],
        snapshot=snapshot,
    )

    assert "vis-network" in html or "vis.js" in html
    assert "n0" in html
    assert "n1" in html
    assert "e1" in html
    assert '"from": "n1"' in html
    assert '"to": "n0"' in html


def test_render_pyvis_html_scales_flow_pressure_and_temperature():
    graph = _simple_graph()
    graph.nodes["v1.Inventory"] = _make_node("v1.Inventory")
    graph.inventory_nodes["v1.Inventory"] = SimpleNamespace()
    graph.nodes["n2"] = _make_node("n2")
    graph.edges["e2"] = _make_edge("e2", "n1", "n2")

    snapshot = VisualizationSnapshot(
        time=1.0,
        pressures={
            "n0": 100_000.0,
            "n1": 200_000.0,
            "n2": 150_000.0,
            "v1.Inventory": 200_000.0,
        },
        flows={"e1": 1.0e-6, "e2": 4.0e-6},
        inventories={
            "v1.Inventory": InventorySnapshot(
                pressure=200_000.0,
                temperature=350.0,
            )
        },
        edge_cells={
            "e1": EdgeCellSnapshot(cell_count=1, average_temperature=300.0),
            "e2": EdgeCellSnapshot(cell_count=1, average_temperature=350.0),
        },
    )

    html = render_pyvis_html(
        graph=graph,
        components=[SimpleNamespace(name="comp")],
        snapshot=snapshot,
    )

    assert '"background": "#E8F1FF"' in html
    assert '"background": "#08519C"' in html
    assert '"border": "#B2182B"' in html
    assert '"color": "#FFF0F0"' in html
    assert '"color": "#B2182B"' in html
    assert '"width": 4.5' in html
    assert '"width": 8.0' in html


def test_render_dashboard_html_builds_analysis_cockpit_payload(workspace_tmp):
    graph = _simple_graph()
    db_path = workspace_tmp / "dashboard.db"
    _write_recorded_db(db_path, graph)

    html = render_dashboard_html(
        db_path,
        graph=graph,
        components=[SimpleNamespace(name="comp")],
    )
    payload = _dashboard_payload(html)

    assert "Plotly.react" in html
    assert 'data-tab="components"' in html
    assert 'data-tab="edges"' in html
    assert 'data-tab="overview"' in html
    assert 'data-tab="signals"' in html
    assert "component-explorer" in html
    assert "edge-explorer" in html
    assert payload["components"][0]["id"] == "comp"
    assert payload["components"][0]["edges"] == ["e1"]
    assert payload["edges"][0]["id"] == "e1"
    assert {group["title"] for group in payload["edges"][0]["signals"]} >= {
        "Flow rate",
        "Average cell temperature",
    }
    assert payload["summary"]["sampleCount"] == 2
    assert payload["summary"]["timeStart"] == 0.0
    assert payload["summary"]["timeEnd"] == 1.0
    assert {chart["tab"] for chart in payload["charts"]} >= {
        "pressures",
        "flows",
        "inventories",
        "temperatures",
    }
    inv_temp_chart = next(
        chart for chart in payload["charts"] if chart["id"] == "inv_temperatures"
    )
    assert inv_temp_chart["tab"] == "temperatures"
    assert '<input data-show-flat-signals type="checkbox">' in html


def test_render_dashboard_html_hides_flat_traces_by_default(workspace_tmp):
    graph = _simple_graph()
    db_path = workspace_tmp / "flat.db"
    _write_recorded_db(db_path, graph)

    payload = _dashboard_payload(render_dashboard_html(db_path))
    pressure_chart = next(
        chart for chart in payload["charts"] if chart["id"] == "node_pressures"
    )
    traces = {trace["name"]: trace for trace in pressure_chart["traces"]}

    assert traces["n0"]["flat"] is False
    assert traces["n0"]["defaultVisible"] is True
    assert traces["n1"]["flat"] is True
    assert traces["n1"]["defaultVisible"] is False


def test_render_dashboard_html_includes_pipe_cell_profiles(workspace_tmp):
    db_path = workspace_tmp / "cells.db"
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE meta (key TEXT NOT NULL PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE node_pressure (
            time REAL NOT NULL,
            node_id TEXT NOT NULL,
            pressure REAL NOT NULL
        );
        CREATE TABLE edge_flow (
            time REAL NOT NULL,
            edge_id TEXT NOT NULL,
            flow_rate REAL NOT NULL
        );
        CREATE TABLE edge_cells (
            edge_id TEXT NOT NULL,
            cell_index INTEGER NOT NULL,
            position_m REAL NOT NULL,
            length_m REAL NOT NULL
        );
        CREATE TABLE cell_state (
            time REAL NOT NULL,
            edge_id TEXT NOT NULL,
            cell_index INTEGER NOT NULL,
            phase TEXT NOT NULL,
            phase_fraction REAL NOT NULL,
            temperature REAL NOT NULL
        );
        CREATE TABLE cell_content (
            time REAL NOT NULL,
            edge_id TEXT NOT NULL,
            cell_index INTEGER NOT NULL,
            phase TEXT NOT NULL,
            species_id TEXT NOT NULL,
            moles REAL NOT NULL
        );
        INSERT INTO meta VALUES ('platform_name', 'cells');
        INSERT INTO node_pressure VALUES (0.0, 'n0', 101325.0);
        INSERT INTO edge_flow VALUES (0.0, 'e0', 0.0);
        INSERT INTO edge_cells VALUES ('e0', 0, 0.0, 0.01);
        INSERT INTO edge_cells VALUES ('e0', 1, 0.01, 0.01);
        INSERT INTO cell_state VALUES (0.0, 'e0', 0, 'liquid', 1.0, 300.0);
        INSERT INTO cell_state VALUES (0.0, 'e0', 1, 'liquid', 0.4, 305.0);
        INSERT INTO cell_state VALUES (0.0, 'e0', 1, 'gas', 0.6, 310.0);
        INSERT INTO cell_content VALUES (0.0, 'e0', 0, 'liquid', 'water', 2.0);
        INSERT INTO cell_content VALUES (0.0, 'e0', 1, 'liquid', 'water', 0.5);
        INSERT INTO cell_content VALUES (0.0, 'e0', 1, 'gas', 'nitrogen', 0.25);
        INSERT INTO cell_content VALUES (1.0, 'e0', 0, 'liquid', 'water', 1.0);
        """)
    conn.close()

    html = render_dashboard_html(db_path)
    payload = _dashboard_payload(html)

    assert 'data-tab="cells"' in html
    assert "Pipe Cells" in html
    assert payload["cellProfiles"]["times"] == [
        {"key": "0", "value": 0.0, "label": "0 s"},
        {"key": "1", "value": 1.0, "label": "1 s"},
    ]
    edge = payload["cellProfiles"]["edges"][0]
    assert edge["edgeId"] == "e0"
    assert edge["cellCount"] == 2
    assert edge["xLabel"] == "Cell position (m)"
    assert [cell["center"] for cell in edge["cells"]] == pytest.approx([0.005, 0.015])

    snapshot = edge["snapshots"]["0"]
    assert snapshot["phaseFractions"]["liquid"] == pytest.approx([1.0, 0.4])
    assert snapshot["phaseFractions"]["gas"] == pytest.approx([0.0, 0.6])
    assert snapshot["temperatures"]["gas"] == [None, 310.0]
    water_key = next(
        item["key"] for item in edge["species"] if item["speciesId"] == "water"
    )
    nitrogen_key = next(
        item["key"] for item in edge["species"] if item["speciesId"] == "nitrogen"
    )
    assert snapshot["contents"][water_key] == pytest.approx([2.0, 0.5])
    assert snapshot["contents"][nitrogen_key] == pytest.approx([0.0, 0.25])
    assert edge["snapshots"]["1"]["contents"][water_key] == pytest.approx([1.0, 0.0])
    assert edge["snapshots"]["1"]["contents"][nitrogen_key] == pytest.approx([0.0, 0.0])

    edge_payload = payload["edges"][0]
    content_group = next(
        group
        for group in edge_payload["signals"]
        if group["title"] == "Average cell content"
    )
    assert content_group["yLabel"] == "Mean moles per cell (mol)"
    content_traces = {trace["name"]: trace for trace in content_group["traces"]}
    assert set(content_traces) == {"gas / nitrogen", "liquid / water"}
    assert content_traces["liquid / water"]["x"] == pytest.approx([0.0, 1.0])
    assert content_traces["liquid / water"]["y"] == pytest.approx([1.25, 0.5])
    assert content_traces["gas / nitrogen"]["y"] == pytest.approx([0.125, 0.0])


def test_render_dashboard_html_averages_cell_content_without_geometry(workspace_tmp):
    db_path = workspace_tmp / "content_without_geometry.db"
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE meta (key TEXT NOT NULL PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE node_pressure (
            time REAL NOT NULL,
            node_id TEXT NOT NULL,
            pressure REAL NOT NULL
        );
        CREATE TABLE edge_flow (
            time REAL NOT NULL,
            edge_id TEXT NOT NULL,
            flow_rate REAL NOT NULL
        );
        CREATE TABLE cell_content (
            time REAL NOT NULL,
            edge_id TEXT NOT NULL,
            cell_index INTEGER NOT NULL,
            phase TEXT NOT NULL,
            species_id TEXT NOT NULL,
            moles REAL NOT NULL
        );
        INSERT INTO meta VALUES ('platform_name', 'content');
        INSERT INTO node_pressure VALUES (0.0, 'n0', 101325.0);
        INSERT INTO edge_flow VALUES (0.0, 'e0', 0.0);
        INSERT INTO cell_content VALUES (0.0, 'e0', 0, 'liquid', 'solvent', 2.0);
        INSERT INTO cell_content VALUES (1.0, 'e0', 0, 'liquid', 'solvent', 1.0);
        INSERT INTO cell_content VALUES (1.0, 'e0', 1, 'liquid', 'solvent', 3.0);
        """)
    conn.close()

    payload = _dashboard_payload(render_dashboard_html(db_path))
    edge_payload = payload["edges"][0]
    content_group = next(
        group
        for group in edge_payload["signals"]
        if group["title"] == "Average cell content"
    )
    trace = content_group["traces"][0]

    assert payload["cellProfiles"]["edges"][0]["xLabel"] == "Cell index"
    assert trace["name"] == "liquid / solvent"
    assert trace["x"] == pytest.approx([0.0, 1.0])
    assert trace["y"] == pytest.approx([1.0, 2.0])


def test_render_dashboard_html_escapes_metadata(workspace_tmp):
    graph = _simple_graph()
    db_path = workspace_tmp / "escaped.db"
    _write_recorded_db(db_path, graph)
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE meta SET value = ? WHERE key = 'platform_name'",
        ("<script>alert(1)</script>&",),
    )
    conn.execute(
        "INSERT INTO node_pressure VALUES (?, ?, ?)",
        (0.0, "<script>alert(1)</script>&", 101_325.0),
    )
    conn.commit()
    conn.close()

    html = render_dashboard_html(db_path)

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;&amp;" in html
    assert "\\u003cscript\\u003ealert(1)\\u003c/script\\u003e\\u0026" in html


def test_render_dashboard_html_handles_missing_optional_tables(workspace_tmp):
    db_path = workspace_tmp / "minimal.db"
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE meta (key TEXT NOT NULL PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE node_pressure (
            time REAL NOT NULL,
            node_id TEXT NOT NULL,
            pressure REAL NOT NULL
        );
        CREATE TABLE edge_flow (
            time REAL NOT NULL,
            edge_id TEXT NOT NULL,
            flow_rate REAL NOT NULL
        );
        INSERT INTO meta VALUES ('platform_name', 'minimal');
        INSERT INTO node_pressure VALUES (0.0, 'n0', 101325.0);
        INSERT INTO edge_flow VALUES (0.0, 'e0', 0.0);
        """)
    conn.close()

    html = render_dashboard_html(db_path)
    payload = _dashboard_payload(html)

    assert "No inventory state traces were recorded." in html
    assert {chart["id"] for chart in payload["charts"]} == {
        "node_pressures",
        "edge_flows",
    }
    assert payload["components"]
    assert payload["edges"][0]["id"] == "e0"


def load_latest_snapshot_from_rows(
    *,
    pressures: dict[str, float],
    flows: dict[str, float],
):
    return VisualizationSnapshot(time=1.0, pressures=pressures, flows=flows)


def _set_server_state(
    workspace_tmp: Path,
    *,
    project: ProjectState | None = None,
    db_path: Path | None = None,
) -> None:
    server._state = SimulationState(
        sim_status=SimStatus.IDLE if project is not None else SimStatus.NO_PROJECT,
        current_t=0.0,
        config=SimConfig(),
        db_path=db_path,
        project=project,
        clock=SimClock(),
        cmd_queue=queue.Queue(),
        db_dir=workspace_tmp,
    )


def _project(workspace_tmp: Path, graph: HydraulicGraph) -> ProjectState:
    component = SimpleNamespace(name="comp")
    return ProjectState(
        project_path=workspace_tmp,
        processes={},
        configs={},
        components={"comp": component},
        graph=graph,
    )


def test_visualization_endpoint_requires_project(workspace_tmp):
    _set_server_state(workspace_tmp, project=None, db_path=None)

    with TestClient(app) as client:
        response = client.get("/simulation/visualization")

    assert response.status_code == 404


def test_visualization_endpoint_requires_db(workspace_tmp):
    graph = _simple_graph()
    _set_server_state(
        workspace_tmp,
        project=_project(workspace_tmp, graph),
        db_path=None,
    )

    with TestClient(app) as client:
        response = client.get("/simulation/visualization")

    assert response.status_code == 404


def test_visualization_endpoint_rejects_db_without_snapshots(workspace_tmp):
    graph = _simple_graph()
    db_path = workspace_tmp / "empty.db"
    rec = Recorder(db_path=db_path, graph=graph, dt=0.1)
    rec.close()
    _set_server_state(
        workspace_tmp,
        project=_project(workspace_tmp, graph),
        db_path=db_path,
    )

    with TestClient(app) as client:
        response = client.get("/simulation/visualization")

    assert response.status_code == 409


def test_visualization_endpoint_writes_visualization_files(workspace_tmp):
    graph = _simple_graph()
    db_path = workspace_tmp / "run.db"
    _write_recorded_db(db_path, graph)
    _set_server_state(
        workspace_tmp,
        project=_project(workspace_tmp, graph),
        db_path=db_path,
    )

    with TestClient(app) as client:
        response = client.get("/simulation/visualization")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    data = response.json()
    graph_html = Path(data["graph_html"])
    dashboard_html = Path(data["dashboard_html"])
    assert graph_html.exists()
    assert dashboard_html.exists()
    assert "n0" in graph_html.read_text(encoding="utf-8")
    dashboard_text = dashboard_html.read_text(encoding="utf-8")
    assert "Plotly.react" in dashboard_text
    assert "e1" in dashboard_text
    payload = _dashboard_payload(dashboard_text)
    assert payload["components"][0]["id"] == "comp"
    assert payload["edges"][0]["origin"] == "n0"
    assert payload["edges"][0]["destination"] == "n1"


def test_visualization_endpoint_rejects_unreadable_db(workspace_tmp):
    graph = _simple_graph()
    db_path = workspace_tmp / "not_sqlite.db"
    db_path.write_text("not sqlite", encoding="utf-8")
    _set_server_state(
        workspace_tmp,
        project=_project(workspace_tmp, graph),
        db_path=db_path,
    )

    with TestClient(app) as client:
        response = client.get("/simulation/visualization")

    assert response.status_code == 422
