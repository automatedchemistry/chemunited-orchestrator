"""Recordings stay small: unchanged frames are skipped, and tube cells are optional."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from chemunited_core.common.enums import ConnectionType
from chemunited_core.connections import EdgeData, EdgeMode
from chemunited_core.figure_registry import COMPONENTS
from chemunited_quantities import ChemUnitQuantity
from chemunited_sim.adapter import compile_graph, resync_component
from chemunited_sim.recorder import Recorder
from chemunited_sim.visualization import load_latest_snapshot, read_node_profile
from chemunited_sim.worker import SimConfig, Worker

DT = 0.1
DYNAMIC_TABLES = (
    "node_pressure",
    "inventory_state",
    "inventory_content",
    "edge_flow",
    "cell_state",
    "cell_content",
    "component_state",
)


def _make(figure: str, name: str, **kwargs):
    definition = COMPONENTS[figure]
    return definition.data_class.from_mode(definition.mode_class(name=name, **kwargs))


def _tube(origin: str, origin_port: int, destination: str, port: int) -> EdgeData:
    return EdgeData.from_mode(
        EdgeMode(
            name=f"{origin}_{origin_port}_{destination}_{port}",
            origin=origin,
            origin_port=origin_port,
            destination=destination,
            destination_port=port,
            classification=ConnectionType.HYDRAULIC,
            length="100 mm",
            diameter="1 mm",
        )
    )


def _platform():
    argon = _make("Source", "argon", setpoint=ChemUnitQuantity("1.2 bar"))
    bottle = _make(
        "GlassBottle",
        "bottle",
        capacity=ChemUnitQuantity("100 ml"),
        top_access=1,
        bottom_access=1,
        pressure_access=True,
    )
    bottle.internal_inventory.liq_content.volume = 80.0e-6
    bottle.internal_inventory.liq_content.initial_species = {"water": 4.0}
    bottle.internal_inventory.gas_content.volume = 20.0e-6
    bottle.internal_inventory.gas_content.initial_species = {"air": 8.0e-4}
    valve = _make("SolenoidValve", "valve")
    receiver = _make("GlassBottle", "receiver", capacity=ChemUnitQuantity("100 ml"))
    components = [argon, bottle, valve, receiver]
    graph = compile_graph(
        components,
        [
            _tube("argon", 1, "bottle", 1),
            _tube("bottle", 2, "valve", 1),
            _tube("valve", 2, "receiver", 1),
        ],
    )
    return graph, components, valve


def _record(db_path: Path, steps_with_valve: list[tuple[int, bool]], **options) -> None:
    """Run the platform, setting the valve to `opened` after each number of steps."""
    graph, components, valve = _platform()
    recorder = Recorder(
        db_path=db_path,
        graph=graph,
        dt=DT,
        record_interval=1.0,
        components={component.name: component for component in components},
        **options,
    )
    worker = Worker(graph, components, SimConfig(dt=DT), recorder=recorder)
    for steps, opened in steps_with_valve:
        valve.apply("open" if opened else "close")
        resync_component(graph, valve)
        for _ in range(steps):
            worker.step()
    recorder.close()


def _times(db_path: Path, table: str = "node_pressure") -> list[float]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(f"SELECT DISTINCT time FROM {table} ORDER BY time")
        return [row[0] for row in rows]


def _count(db_path: Path, table: str) -> int:
    with sqlite3.connect(db_path) as conn:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_by_default_every_interval_is_written(tmp_path) -> None:
    db = tmp_path / "run.db"

    _record(db, [(100, False)])

    assert _times(db) == pytest.approx([float(i) for i in range(10)], abs=1e-6)


def test_an_idle_run_keeps_only_its_first_and_last_frames(tmp_path) -> None:
    db = tmp_path / "run.db"

    # The first frames still settle, so give it time, then look at the tail.
    _record(db, [(600, False)], skip_unchanged=True)

    times = _times(db)
    assert times[0] == 0.0
    assert times[-1] == pytest.approx(59.0, abs=1e-6)
    assert len(times) < 10


def test_movement_is_recorded_at_every_interval(tmp_path) -> None:
    db = tmp_path / "run.db"

    _record(db, [(600, False), (100, True)], skip_unchanged=True)

    times = _times(db)
    during = [t for t in times if t >= 60.0 - 1e-6]
    assert during == pytest.approx([60.0 + i for i in range(10)], abs=1e-6)


def test_a_change_is_preceded_by_the_frame_just_before_it(tmp_path) -> None:
    db = tmp_path / "run.db"

    _record(db, [(600, False), (100, True)], skip_unchanged=True)

    times = _times(db)
    assert any(t == pytest.approx(59.0, abs=1e-6) for t in times)
    with sqlite3.connect(db) as conn:
        flow_before = conn.execute(
            "SELECT flow_rate FROM edge_flow WHERE edge_id = 'bottle_2_valve_1' "
            "AND ABS(time - 59.0) < 1e-6"
        ).fetchone()[0]
        flow_after = conn.execute(
            "SELECT flow_rate FROM edge_flow WHERE edge_id = 'bottle_2_valve_1' "
            "AND ABS(time - 60.0) < 1e-6"
        ).fetchone()[0]
    assert abs(flow_before) < 1e-9
    assert flow_after > 1e-9


def test_a_held_frame_copies_the_frame_it_stands_for(tmp_path) -> None:
    db = tmp_path / "run.db"

    _record(db, [(600, False)], skip_unchanged=True)

    times = _times(db)
    last_written, held = times[-2], times[-1]
    with sqlite3.connect(db) as conn:
        for table, columns in (
            ("node_pressure", "node_id, pressure"),
            ("inventory_content", "node_id, phase, species_id, moles, volume"),
            ("edge_flow", "edge_id, flow_rate"),
            ("cell_state", "edge_id, cell_index, phase, phase_fraction, temperature"),
        ):
            query = f"SELECT {columns} FROM {table} WHERE time = ? ORDER BY 1, 2, 3"
            if table in ("node_pressure", "edge_flow"):
                query = f"SELECT {columns} FROM {table} WHERE time = ? ORDER BY 1"
            first = conn.execute(query, (last_written,)).fetchall()
            second = conn.execute(query, (held,)).fetchall()
            assert first == second, table
            assert first, table


def test_every_recorded_time_is_a_complete_frame(tmp_path) -> None:
    db = tmp_path / "run.db"

    _record(db, [(300, False), (50, True), (300, False)], skip_unchanged=True)

    expected = _times(db)
    for table in DYNAMIC_TABLES:
        assert _times(db, table) == expected, table


def test_skipped_frames_leave_the_end_state_and_history_readable(tmp_path) -> None:
    db = tmp_path / "run.db"

    _record(db, [(300, False), (50, True), (300, False)], skip_unchanged=True)

    latest = load_latest_snapshot(db)
    assert latest.time == pytest.approx(64.0, abs=1e-6)
    profile = read_node_profile(db, "receiver.Inventory")
    moles = [point["moles"] for point in profile["content"]["liquid"]["water"]]
    assert moles == sorted(moles)
    assert moles[-1] > 0.0


def test_results_match_the_full_recording_at_the_times_both_have(tmp_path) -> None:
    full = tmp_path / "full.db"
    skipped = tmp_path / "skipped.db"
    run = [(300, False), (50, True), (300, False)]

    _record(full, run)
    _record(skipped, run, skip_unchanged=True)

    assert len(_times(skipped)) < len(_times(full)) / 3
    query = "SELECT node_id, moles, volume FROM inventory_content WHERE time = ?"
    with sqlite3.connect(full) as a, sqlite3.connect(skipped) as b:
        for t in _times(skipped):
            rows_full = sorted(a.execute(query, (t,)).fetchall())
            rows_skipped = sorted(b.execute(query, (t,)).fetchall())
            assert len(rows_full) == len(rows_skipped)
            for one, other in zip(rows_full, rows_skipped, strict=True):
                assert one[0] == other[0]
                assert one[1] == pytest.approx(other[1], rel=1e-3, abs=1e-9)
                assert one[2] == pytest.approx(other[2], abs=1e-9)


def test_closing_twice_writes_the_held_frame_once(tmp_path) -> None:
    db = tmp_path / "run.db"
    graph, components, _valve = _platform()
    recorder = Recorder(
        db_path=db, graph=graph, dt=DT, record_interval=1.0, skip_unchanged=True
    )
    worker = Worker(graph, components, SimConfig(dt=DT), recorder=recorder)
    for _ in range(600):
        worker.step()

    recorder.close()
    recorder.close()

    assert _times(db)[-1] == pytest.approx(59.0, abs=1e-6)
    assert len(_times(db)) == len(set(_times(db)))


def test_cells_can_be_left_out(tmp_path) -> None:
    db = tmp_path / "run.db"

    _record(db, [(50, False), (50, True)], record_cells=False)

    assert _count(db, "edge_cells") == 0
    assert _count(db, "cell_state") == 0
    assert _count(db, "cell_content") == 0
    assert _count(db, "node_pressure") > 0
    assert _count(db, "inventory_content") > 0
    with sqlite3.connect(db) as conn:
        meta = dict(conn.execute("SELECT key, value FROM meta"))
    assert meta["record_cells"] == "False"


def test_a_record_interval_shorter_than_a_step_records_every_step(tmp_path) -> None:
    graph, components, _valve = _platform()
    db = tmp_path / "run.db"
    recorder = Recorder(db_path=db, graph=graph, dt=DT, record_interval=0.01)
    worker = Worker(graph, components, SimConfig(dt=DT), recorder=recorder)

    for _ in range(3):
        worker.step()
    recorder.close()

    assert len(_times(db)) == 3
