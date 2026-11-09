"""The readers behind the simulation window work on a recording with skipped frames."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from chemunited.simulation.final_state import list_recorded_times, load_edge_cells
from chemunited.simulation.playback import SimulationPlayback
from chemunited.simulation.simulate_report import SimDbReader
from chemunited_core.common.enums import ConnectionType
from chemunited_core.connections import EdgeData, EdgeMode
from chemunited_core.figure_registry import COMPONENTS
from chemunited_quantities import ChemUnitQuantity
from chemunited_sim.adapter import compile_graph, resync_component
from chemunited_sim.recorder import Recorder
from chemunited_sim.worker import SimConfig, Worker


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


@pytest.fixture
def recording(tmp_path: Path) -> Path:
    """Idle, then a valve opens and liquid moves, then idle again."""
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
    db_path = tmp_path / "run.db"
    recorder = Recorder(
        db_path=db_path,
        graph=graph,
        dt=0.1,
        record_interval=1.0,
        components={component.name: component for component in components},
        skip_unchanged=True,
    )
    worker = Worker(graph, components, SimConfig(dt=0.1), recorder=recorder)
    for steps, opened in ((300, False), (50, True), (300, False)):
        valve.apply("open" if opened else "close")
        resync_component(graph, valve)
        for _ in range(steps):
            worker.step()
    recorder.close()
    return db_path


def test_recorded_times_skip_the_idle_stretches(recording: Path) -> None:
    conn = sqlite3.connect(f"file:{recording}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        times = list_recorded_times(conn)
    finally:
        conn.close()

    assert times[0] == 0.0
    assert times[-1] == pytest.approx(64.0, abs=1e-6)
    assert len(times) < 65 / 3


def test_every_recorded_time_has_its_tube_contents(recording: Path) -> None:
    conn = sqlite3.connect(f"file:{recording}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        for t in list_recorded_times(conn):
            cells = load_edge_cells(conn, "valve_2_receiver_1", t)
            assert cells, t
    finally:
        conn.close()


def test_playback_opens_a_recording_with_skipped_frames(recording: Path) -> None:
    playback = SimulationPlayback.open(recording)

    assert playback is not None
    try:
        assert playback.frame_count == len(playback.times) >= 2
        assert playback.times == sorted(playback.times)
    finally:
        playback.close()


def test_charts_read_a_recording_with_skipped_frames(recording: Path) -> None:
    reader = SimDbReader(recording)
    try:
        content = reader.content("receiver")
        flows = reader.flow("bottle_2_valve_1")
    finally:
        reader.close()

    water = next(v for k, v in content.items() if k.endswith("liquid / water"))
    assert water[1] == sorted(water[1])
    assert water[1][-1] > 0.0
    _, flow_series = next(iter(flows.values()))
    assert max(flow_series) > 1.0
    assert abs(flow_series[0]) < 1.0
    assert abs(flow_series[-1]) < 1.0
