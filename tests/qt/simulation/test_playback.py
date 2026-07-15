from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from chemunited_core.components import VesselComponentData, VesselMode
from chemunited_core.components.internals import DEFAULT_INVENTORY_KEY
from chemunited_quantities import ChemUnitQuantity
from chemunited_sim.recorder.schema import create_all_tables

from chemunited.simulation.playback import SimulationPlayback


def qty(value: str) -> ChemUnitQuantity:
    return ChemUnitQuantity(value)


class _FakeComponent:
    """Duck-typed stand-in for a UtensilManager: exposes .inf and .graph.sync_visuals()."""

    def __init__(self, inf) -> None:
        self.inf = inf
        self.sync_calls = 0
        self.graph = self

    def sync_visuals(self) -> None:
        self.sync_calls += 1


class _FakeConnections:
    def __init__(self, hydraulic: dict) -> None:
        self.hydraulic = hydraulic


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    create_all_tables(conn)
    return conn


def test_open_returns_none_for_missing_db(tmp_path: Path) -> None:
    assert SimulationPlayback.open(tmp_path / "missing.db") is None


def test_open_loads_sorted_times(tmp_path: Path) -> None:
    db_path = tmp_path / "sim.db"
    conn = _connect(db_path)
    conn.executemany(
        "INSERT INTO node_pressure (time, node_id, pressure) VALUES (?, ?, ?)",
        [(2.0, "a.1", 101325.0), (0.5, "a.1", 101325.0), (1.5, "a.1", 101325.0)],
    )
    conn.commit()
    conn.close()

    playback = SimulationPlayback.open(db_path)

    assert playback is not None
    assert playback.times == [0.5, 1.5, 2.0]
    assert playback.frame_count == 3
    playback.close()


def test_open_handles_empty_db_returns_playback_with_no_times(tmp_path: Path) -> None:
    db_path = tmp_path / "sim.db"
    _connect(db_path).close()

    playback = SimulationPlayback.open(db_path)

    assert playback is not None
    assert playback.times == []
    assert playback.frame_count == 0
    playback.close()


def test_apply_at_time_applies_requested_snapshot_not_latest(tmp_path: Path) -> None:
    db_path = tmp_path / "sim.db"
    conn = _connect(db_path)
    conn.executemany(
        "INSERT INTO inventory_content "
        "(time, node_id, phase, species_id, moles, volume) VALUES (?, ?, ?, ?, ?, ?)",
        [
            (1.0, "flask1.Inventory", "liquid", "red_dye", 0.01, 1e-6),
            (2.0, "flask1.Inventory", "liquid", "red_dye", 0.05, 5e-6),
        ],
    )
    conn.commit()
    conn.close()

    vessel = VesselComponentData.from_mode(
        VesselMode(name="flask1", capacity=qty("10 ml"), top_access=1, bottom_access=1)
    )
    component = _FakeComponent(inf=vessel)
    playback = SimulationPlayback.open(db_path)
    assert playback is not None

    playback.apply_at_time(1.0, {"flask1": component}, _FakeConnections({}))

    inventory = vessel.internal_inventories[DEFAULT_INVENTORY_KEY]
    assert inventory.liq_content.initial_species == {"red_dye": 0.01}
    playback.close()


def test_close_makes_further_queries_fail(tmp_path: Path) -> None:
    db_path = tmp_path / "sim.db"
    _connect(db_path).close()

    playback = SimulationPlayback.open(db_path)
    assert playback is not None

    playback.close()

    with pytest.raises(sqlite3.ProgrammingError):
        playback._conn.execute("SELECT 1")
