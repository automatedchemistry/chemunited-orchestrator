"""Tests for the recorder module.

Covers:
- Import smoke test
- build_cell_definitions: edge slicing, last-cell remainder, role filtering
- Recorder.should_record: integer-tick arithmetic
- Recorder.__init__: static tables (meta, edge_cells) written correctly
- Recorder.record: all six dynamic tables written atomically
- Recorder.close: idempotent
"""

from __future__ import annotations

import json
import math
import sqlite3
from collections import deque

import pytest
from chemunited_core.common.enums import PhaseKind
from chemunited_core.components import ComponentData
from chemunited_core.components.enums import InternalEdgeRole
from chemunited_core.figure_registry import SolenoidValve2WayData, SolenoidValveData
from chemunited_core.figure_registry.rotary_valve import RotaryValveData
from loguru import logger

from chemunited_sim.adapter.models import HydraulicEdge, HydraulicGraph, HydraulicNode
from chemunited_sim.hydraulics.models import HydraulicState
from chemunited_sim.inventory.models import InventoryState
from chemunited_sim.recorder import (
    CellDefinition,
    Recorder,
    RecorderWriteError,
    build_cell_definitions,
)
from chemunited_sim.transport.models import Pocket, TransportState

# ---------------------------------------------------------------------------
# Helpers — minimal graph factory
# ---------------------------------------------------------------------------


def _make_node(node_id: str) -> HydraulicNode:
    return HydraulicNode(node_id=node_id, boundary=None, is_hub=False, component="comp")


def _make_edge(
    edge_id: str,
    origin: str,
    dest: str,
    *,
    length: float = 1.0,
    diameter: float = 0.004,
    role: InternalEdgeRole = InternalEdgeRole.TRANSPORT,
    resistance_override: float | None = None,
) -> HydraulicEdge:
    return HydraulicEdge(
        edge_id=edge_id,
        origin_node_id=origin,
        destination_node_id=dest,
        length=length,
        diameter=diameter,
        role=role,
        resistance_override=resistance_override,
        component="comp",
        is_external=False,
    )


def _simple_graph() -> HydraulicGraph:
    """Graph with one TRANSPORT edge (1 m long, 4 mm diameter)."""
    graph = HydraulicGraph()
    graph.nodes["n0"] = _make_node("n0")
    graph.nodes["n1"] = _make_node("n1")
    graph.edges["e1"] = _make_edge("e1", "n0", "n1", length=1.0, diameter=0.004)
    return graph


# ---------------------------------------------------------------------------
# 1. Import smoke test
# ---------------------------------------------------------------------------


def test_imports():
    assert CellDefinition is not None
    assert Recorder is not None
    assert RecorderWriteError is not None
    assert build_cell_definitions is not None


# ---------------------------------------------------------------------------
# 2. build_cell_definitions
# ---------------------------------------------------------------------------


class TestBuildCellDefinitions:
    def test_single_cell_when_edge_shorter_than_cell_length(self):
        graph = HydraulicGraph()
        graph.nodes["a"] = _make_node("a")
        graph.nodes["b"] = _make_node("b")
        graph.edges["short"] = _make_edge(
            "short", "a", "b", length=0.005, diameter=0.004
        )

        cells = build_cell_definitions(graph, cell_length_m=0.01)

        assert len(cells) == 1
        assert cells[0].edge_id == "short"
        assert cells[0].cell_index == 0
        assert cells[0].position_m == pytest.approx(0.0)
        assert cells[0].length_m == pytest.approx(0.005)

    def test_last_cell_absorbs_remainder(self):
        # 0.025 m / 0.01 m = 2.5 → ceil = 3 cells
        graph = HydraulicGraph()
        graph.nodes["a"] = _make_node("a")
        graph.nodes["b"] = _make_node("b")
        graph.edges["rem"] = _make_edge("rem", "a", "b", length=0.025, diameter=0.004)

        cells = build_cell_definitions(graph, cell_length_m=0.01)

        assert len(cells) == 3
        assert cells[0].length_m == pytest.approx(0.01)
        assert cells[1].length_m == pytest.approx(0.01)
        assert cells[2].length_m == pytest.approx(0.005)  # remainder
        assert cells[2].position_m == pytest.approx(0.02)

    def test_junction_edges_excluded(self):
        graph = HydraulicGraph()
        graph.nodes["a"] = _make_node("a")
        graph.nodes["b"] = _make_node("b")
        graph.edges["junc"] = _make_edge(
            "junc",
            "a",
            "b",
            length=1.0,
            diameter=0.004,
            role=InternalEdgeRole.JUNCTION,
        )

        cells = build_cell_definitions(graph, cell_length_m=0.01)
        assert cells == []

    def test_zero_diameter_excluded(self):
        graph = HydraulicGraph()
        graph.nodes["a"] = _make_node("a")
        graph.nodes["b"] = _make_node("b")
        graph.edges["bpr"] = _make_edge("bpr", "a", "b", length=1.0, diameter=0.0)

        cells = build_cell_definitions(graph, cell_length_m=0.01)
        assert cells == []

    def test_sorted_by_edge_id_then_cell_index(self):
        graph = HydraulicGraph()
        for name in ("zz", "aa"):
            graph.nodes[f"{name}_0"] = _make_node(f"{name}_0")
            graph.nodes[f"{name}_1"] = _make_node(f"{name}_1")
            graph.edges[name] = _make_edge(
                name, f"{name}_0", f"{name}_1", length=0.025, diameter=0.004
            )

        cells = build_cell_definitions(graph, cell_length_m=0.01)
        edge_ids = [c.edge_id for c in cells]
        assert edge_ids[:3] == ["aa", "aa", "aa"]
        assert edge_ids[3:] == ["zz", "zz", "zz"]


# ---------------------------------------------------------------------------
# 3. Recorder.should_record
# ---------------------------------------------------------------------------


class TestShouldRecord:
    def _recorder(self, tmp_path, dt=0.1, record_interval=1.0):
        graph = _simple_graph()
        return Recorder(
            db_path=tmp_path / "test.db",
            graph=graph,
            dt=dt,
            record_interval=record_interval,
        )

    def test_records_at_t_zero(self, tmp_path):
        r = self._recorder(tmp_path)
        assert r.should_record(0.0) is True

    def test_records_at_exact_multiples(self, tmp_path):
        r = self._recorder(tmp_path, dt=0.1, record_interval=1.0)
        assert r.should_record(1.0) is True
        assert r.should_record(2.0) is True
        assert r.should_record(5.0) is True

    def test_skips_non_multiples(self, tmp_path):
        r = self._recorder(tmp_path, dt=0.1, record_interval=1.0)
        assert r.should_record(0.3) is False
        assert r.should_record(0.7) is False

    def test_float_drift_robustness(self, tmp_path):
        # Accumulate 10 × 0.1 steps — float sum may drift slightly past 1.0
        r = self._recorder(tmp_path, dt=0.1, record_interval=1.0)
        t = 0.0
        for _ in range(10):
            t += 0.1
        assert r.should_record(t) is True

    def test_warns_on_non_multiple_interval(self, tmp_path):
        graph = _simple_graph()
        log_messages: list[str] = []
        handler_id = logger.add(
            lambda message: log_messages.append(message.record["message"]),
            level="WARNING",
        )
        try:
            Recorder(
                db_path=tmp_path / "warn.db",
                graph=graph,
                dt=0.1,
                record_interval=0.35,
            )
        finally:
            logger.remove(handler_id)
        assert any("not an exact multiple" in message for message in log_messages)

    def teardown_method(self, method):
        pass  # pytest tmp_path handles cleanup


# ---------------------------------------------------------------------------
# 4. Static tables written at construction
# ---------------------------------------------------------------------------


class TestStaticTables:
    def _open_ro(self, db_path):
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def test_meta_rows_written(self, tmp_path):
        graph = _simple_graph()
        rec = Recorder(
            db_path=tmp_path / "meta.db",
            graph=graph,
            dt=0.1,
            record_interval=2.0,
            platform_name="test-platform",
        )
        rec.close()

        conn = self._open_ro(tmp_path / "meta.db")
        rows = {
            r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM meta")
        }
        conn.close()

        assert rows["dt"] == "0.1"
        assert rows["record_interval"] == "2.0"
        assert rows["platform_name"] == "test-platform"
        assert "timestamp" in rows

    def test_edge_cells_written_for_transport_edges(self, tmp_path):
        graph = HydraulicGraph()
        graph.nodes["a"] = _make_node("a")
        graph.nodes["b"] = _make_node("b")
        # 0.025 m → 3 cells at 0.01 m each
        graph.edges["e1"] = _make_edge("e1", "a", "b", length=0.025, diameter=0.004)

        rec = Recorder(db_path=tmp_path / "cells.db", graph=graph, dt=0.1)
        rec.close()

        conn = self._open_ro(tmp_path / "cells.db")
        rows = list(conn.execute("SELECT * FROM edge_cells ORDER BY cell_index"))
        conn.close()

        assert len(rows) == 3
        assert rows[0]["edge_id"] == "e1"
        assert rows[0]["cell_index"] == 0
        assert rows[2]["cell_index"] == 2

    def test_no_cells_for_junction_edge(self, tmp_path):
        graph = HydraulicGraph()
        graph.nodes["a"] = _make_node("a")
        graph.nodes["b"] = _make_node("b")
        graph.edges["junc"] = _make_edge(
            "junc",
            "a",
            "b",
            length=1.0,
            diameter=0.004,
            role=InternalEdgeRole.JUNCTION,
        )

        rec = Recorder(db_path=tmp_path / "junc.db", graph=graph, dt=0.1)
        rec.close()

        conn = self._open_ro(tmp_path / "junc.db")
        count = conn.execute("SELECT COUNT(*) FROM edge_cells").fetchone()[0]
        conn.close()
        assert count == 0

    def test_overwrites_existing_db(self, tmp_path):
        db = tmp_path / "overwrite.db"
        graph = _simple_graph()

        r1 = Recorder(db_path=db, graph=graph, dt=0.1, platform_name="first")
        r1.close()

        r2 = Recorder(db_path=db, graph=graph, dt=0.1, platform_name="second")
        r2.close()

        conn = self._open_ro(db)
        rows = {
            r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM meta")
        }
        conn.close()
        assert rows["platform_name"] == "second"


# ---------------------------------------------------------------------------
# 5. Recorder.record — dynamic tables
# ---------------------------------------------------------------------------


def _make_hyd_state():
    return HydraulicState(
        pressures={"n0": 200_000.0, "n1": 101_325.0},
        flows={"e1": 1e-6},
    )


def _make_inv_state(node_id: str = "v1.Inventory") -> InventoryState:
    return InventoryState(
        node_id=node_id,
        capacity=1e-3,
        pressure=200_000.0,
        temperature=298.15,
        liq_volume=5e-4,
        gas_volume=5e-4,
        liq_species_moles={"water": 10.0},
        gas_species_moles={},
    )


def _make_transport_state(graph: HydraulicGraph) -> TransportState:
    """Fill each TRANSPORT edge with a single gas pocket spanning the whole edge."""
    edge_queues: dict[str, deque[Pocket]] = {}
    for eid, edge in graph.edges.items():
        if edge.role != InternalEdgeRole.TRANSPORT or edge.diameter <= 0.0:
            continue
        area = math.pi * (edge.diameter / 2.0) ** 2
        volume = edge.length * area
        pocket = Pocket(
            phase_kind=PhaseKind.GAS,
            volume=volume,
            species_moles={},
            temperature=298.15,
            pressure=101_325.0,
        )
        edge_queues[eid] = deque([pocket])
    return TransportState(edge_queues=edge_queues)


class TestRecord:
    def _setup(self, tmp_path):
        graph = _simple_graph()
        rec = Recorder(
            db_path=tmp_path / "rec.db", graph=graph, dt=0.1, record_interval=1.0
        )
        return rec, graph, tmp_path / "rec.db"

    def _open_ro(self, db_path):
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def test_noop_when_not_due(self, tmp_path):
        rec, graph, db_path = self._setup(tmp_path)
        hyd = _make_hyd_state()
        ts = _make_transport_state(graph)
        inv = {"v1.Inventory": _make_inv_state()}

        # t=0.5 is not a record time (interval=1.0, dt=0.1 → every 10 ticks)
        rec.record(0.5, hyd, ts, inv)
        rec.close()

        conn = self._open_ro(db_path)
        count = conn.execute("SELECT COUNT(*) FROM node_pressure").fetchone()[0]
        conn.close()
        assert count == 0

    def test_node_pressure_written(self, tmp_path):
        rec, graph, db_path = self._setup(tmp_path)
        hyd = _make_hyd_state()
        ts = _make_transport_state(graph)
        inv = {"v1.Inventory": _make_inv_state()}

        rec.record(0.0, hyd, ts, inv)
        rec.close()

        conn = self._open_ro(db_path)
        rows = list(conn.execute("SELECT * FROM node_pressure ORDER BY node_id"))
        conn.close()

        assert len(rows) == 2
        by_id = {r["node_id"]: r["pressure"] for r in rows}
        assert by_id["n0"] == pytest.approx(200_000.0)
        assert by_id["n1"] == pytest.approx(101_325.0)

    def test_edge_flow_written(self, tmp_path):
        rec, graph, db_path = self._setup(tmp_path)
        hyd = _make_hyd_state()
        ts = _make_transport_state(graph)
        inv = {"v1.Inventory": _make_inv_state()}

        rec.record(0.0, hyd, ts, inv)
        rec.close()

        conn = self._open_ro(db_path)
        rows = list(conn.execute("SELECT * FROM edge_flow"))
        conn.close()

        assert len(rows) == 1
        assert rows[0]["edge_id"] == "e1"
        assert rows[0]["flow_rate"] == pytest.approx(1e-6)

    def test_inventory_state_written(self, tmp_path):
        rec, graph, db_path = self._setup(tmp_path)
        hyd = _make_hyd_state()
        ts = _make_transport_state(graph)
        inv = {"v1.Inventory": _make_inv_state()}

        rec.record(0.0, hyd, ts, inv)
        rec.close()

        conn = self._open_ro(db_path)
        rows = list(conn.execute("SELECT * FROM inventory_state"))
        conn.close()

        assert len(rows) == 1
        assert rows[0]["node_id"] == "v1.Inventory"
        assert rows[0]["pressure"] == pytest.approx(200_000.0)
        assert rows[0]["temperature"] == pytest.approx(298.15)

    def test_inventory_content_liquid_species(self, tmp_path):
        rec, graph, db_path = self._setup(tmp_path)
        hyd = _make_hyd_state()
        ts = _make_transport_state(graph)
        inv = {"v1.Inventory": _make_inv_state()}

        rec.record(0.0, hyd, ts, inv)
        rec.close()

        conn = self._open_ro(db_path)
        rows = list(
            conn.execute("SELECT * FROM inventory_content WHERE phase='liquid'")
        )
        conn.close()

        assert len(rows) == 1
        assert rows[0]["species_id"] == "water"
        assert rows[0]["moles"] == pytest.approx(10.0)

    def test_inventory_content_carrier_sentinel_for_empty_gas(self, tmp_path):
        rec, graph, db_path = self._setup(tmp_path)
        hyd = _make_hyd_state()
        ts = _make_transport_state(graph)
        inv = {"v1.Inventory": _make_inv_state()}  # gas_species_moles = {}

        rec.record(0.0, hyd, ts, inv)
        rec.close()

        conn = self._open_ro(db_path)
        rows = list(conn.execute("SELECT * FROM inventory_content WHERE phase='gas'"))
        conn.close()

        assert len(rows) == 1
        assert rows[0]["species_id"] == "__carrier__"
        assert rows[0]["moles"] == pytest.approx(0.0)

    def test_cell_state_written_for_transport_edge(self, tmp_path):
        # Edge e1: 1.0 m, 4 mm diameter → 100 cells at 0.01 m
        rec, graph, db_path = self._setup(tmp_path)
        hyd = _make_hyd_state()
        ts = _make_transport_state(graph)
        inv = {}

        rec.record(0.0, hyd, ts, inv)
        rec.close()

        conn = self._open_ro(db_path)
        count = conn.execute("SELECT COUNT(*) FROM cell_state").fetchone()[0]
        conn.close()

        # One gas pocket fills all 100 cells → 100 cell_state rows
        assert count == 100

    def test_cell_content_empty_for_carrier_pocket(self, tmp_path):
        # Gas pocket with no species_moles → no cell_content rows
        rec, graph, db_path = self._setup(tmp_path)
        hyd = _make_hyd_state()
        ts = _make_transport_state(graph)
        inv = {}

        rec.record(0.0, hyd, ts, inv)
        rec.close()

        conn = self._open_ro(db_path)
        count = conn.execute("SELECT COUNT(*) FROM cell_content").fetchone()[0]
        conn.close()

        assert count == 0

    def test_cell_content_written_when_species_present(self, tmp_path):
        graph = _simple_graph()
        rec = Recorder(
            db_path=tmp_path / "sp.db", graph=graph, dt=0.1, record_interval=1.0
        )

        hyd = _make_hyd_state()
        area = math.pi * (0.004 / 2.0) ** 2
        vol = 1.0 * area
        pocket = Pocket(
            phase_kind=PhaseKind.LIQUID,
            volume=vol,
            species_moles={"water": 5.0},
            temperature=298.15,
            pressure=200_000.0,
        )
        ts = TransportState(edge_queues={"e1": deque([pocket])})

        rec.record(0.0, hyd, ts, {})
        rec.close()

        conn = sqlite3.connect(f"file:{tmp_path / 'sp.db'}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        rows = list(conn.execute("SELECT * FROM cell_content WHERE species_id='water'"))
        conn.close()

        assert len(rows) == 100  # one per cell

    def test_multiple_record_steps_appended(self, tmp_path):
        rec, graph, db_path = self._setup(tmp_path)
        hyd = _make_hyd_state()
        ts = _make_transport_state(graph)
        inv = {}

        rec.record(0.0, hyd, ts, inv)
        rec.record(1.0, hyd, ts, inv)
        rec.record(2.0, hyd, ts, inv)
        rec.close()

        conn = self._open_ro(db_path)
        times = [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT time FROM node_pressure ORDER BY time"
            )
        ]
        conn.close()

        assert times == pytest.approx([0.0, 1.0, 2.0])

    def test_phase_fraction_correct(self, tmp_path):
        # Single pocket fills exactly one cell → phase_fraction == 1.0
        graph = HydraulicGraph()
        graph.nodes["a"] = _make_node("a")
        graph.nodes["b"] = _make_node("b")
        # Edge length = cell_length_m exactly → 1 cell
        graph.edges["e1"] = _make_edge("e1", "a", "b", length=0.01, diameter=0.004)

        rec = Recorder(
            db_path=tmp_path / "frac.db", graph=graph, dt=0.1, record_interval=1.0
        )
        hyd = HydraulicState(
            pressures={"a": 200_000.0, "b": 101_325.0}, flows={"e1": 1e-6}
        )
        area = math.pi * (0.004 / 2.0) ** 2
        pocket = Pocket(
            phase_kind=PhaseKind.GAS,
            volume=0.01 * area,
            species_moles={},
            temperature=298.15,
            pressure=101_325.0,
        )
        ts = TransportState(edge_queues={"e1": deque([pocket])})

        rec.record(0.0, hyd, ts, {})
        rec.close()

        conn = sqlite3.connect(f"file:{tmp_path / 'frac.db'}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        rows = list(conn.execute("SELECT phase_fraction, temperature FROM cell_state"))
        conn.close()

        assert len(rows) == 1
        assert rows[0]["phase_fraction"] == pytest.approx(1.0)
        assert rows[0]["temperature"] == pytest.approx(298.15)


# ---------------------------------------------------------------------------
# 6. Recorder.record — component_state (discrete state)
# ---------------------------------------------------------------------------


class TestComponentState:
    def _setup(self, tmp_path, components, db_name="cs.db"):
        graph = _simple_graph()
        rec = Recorder(
            db_path=tmp_path / db_name,
            graph=graph,
            dt=0.1,
            record_interval=1.0,
            components=components,
        )
        return rec, tmp_path / db_name

    def _open_ro(self, db_path):
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def test_rotary_valve_rotor_ports_recorded(self, tmp_path):
        valve = RotaryValveData(name="Valve1")
        valve.rotor_ports = [(0, 1, None, None, None, None), (0,)]
        rec, db_path = self._setup(tmp_path, {"Valve1": valve})

        rec.record(0.0, _make_hyd_state(), TransportState(edge_queues={}), {})
        rec.close()

        conn = self._open_ro(db_path)
        rows = list(
            conn.execute("SELECT * FROM component_state WHERE component='Valve1'")
        )
        conn.close()

        assert len(rows) == 1
        state = json.loads(rows[0]["state"])
        assert state == {"rotor_ports": [[0, 1, None, None, None, None], [0]]}

    def test_solenoid_valve_opened_recorded(self, tmp_path):
        solenoid = SolenoidValveData(name="Sol1")
        solenoid.opened = False
        rec, db_path = self._setup(tmp_path, {"Sol1": solenoid})

        rec.record(0.0, _make_hyd_state(), TransportState(edge_queues={}), {})
        rec.close()

        conn = self._open_ro(db_path)
        rows = list(
            conn.execute("SELECT * FROM component_state WHERE component='Sol1'")
        )
        conn.close()

        assert len(rows) == 1
        assert json.loads(rows[0]["state"]) == {"opened": False}

    def test_solenoid_2way_opened_recorded(self, tmp_path):
        solenoid = SolenoidValve2WayData(name="Sol2")
        rec, db_path = self._setup(tmp_path, {"Sol2": solenoid})

        rec.record(0.0, _make_hyd_state(), TransportState(edge_queues={}), {})
        rec.close()

        conn = self._open_ro(db_path)
        rows = list(
            conn.execute("SELECT * FROM component_state WHERE component='Sol2'")
        )
        conn.close()

        assert len(rows) == 1
        assert json.loads(rows[0]["state"]) == {"opened": True}

    def test_component_without_discrete_state_not_recorded(self, tmp_path):
        plain = ComponentData(name="Plain1")
        rec, db_path = self._setup(tmp_path, {"Plain1": plain})

        rec.record(0.0, _make_hyd_state(), TransportState(edge_queues={}), {})
        rec.close()

        conn = self._open_ro(db_path)
        count = conn.execute("SELECT COUNT(*) FROM component_state").fetchone()[0]
        conn.close()
        assert count == 0

    def test_omitting_components_param_writes_no_rows(self, tmp_path):
        graph = _simple_graph()
        rec = Recorder(
            db_path=tmp_path / "no_components.db",
            graph=graph,
            dt=0.1,
            record_interval=1.0,
        )

        rec.record(0.0, _make_hyd_state(), _make_transport_state(graph), {})
        rec.close()

        conn = self._open_ro(tmp_path / "no_components.db")
        count = conn.execute("SELECT COUNT(*) FROM component_state").fetchone()[0]
        conn.close()
        assert count == 0


# ---------------------------------------------------------------------------
# 7. Recorder.close — idempotent
# ---------------------------------------------------------------------------


class TestClose:
    def test_close_is_idempotent(self, tmp_path):
        graph = _simple_graph()
        rec = Recorder(db_path=tmp_path / "c.db", graph=graph, dt=0.1)
        rec.close()
        rec.close()  # must not raise

    def test_record_after_close_raises(self, tmp_path):
        graph = _simple_graph()
        rec = Recorder(db_path=tmp_path / "c2.db", graph=graph, dt=0.1)
        rec.close()
        hyd = _make_hyd_state()
        ts = _make_transport_state(graph)
        with pytest.raises(RecorderWriteError, match="after close"):
            rec.record(0.0, hyd, ts, {})
