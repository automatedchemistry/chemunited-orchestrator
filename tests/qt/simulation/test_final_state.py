from __future__ import annotations

import sqlite3
from pathlib import Path

from chemunited_core.common.enums import PhaseKind
from chemunited_core.components import VesselComponentData, VesselMode
from chemunited_core.components.internals import DEFAULT_INVENTORY_KEY
from chemunited_core.components.plugflow import PlugFlowComponentData
from chemunited_core.figure_registry import SolenoidValve2WayData, SolenoidValveData
from chemunited_core.figure_registry.rotary_valve import RotaryValveData
from chemunited_quantities import ChemUnitQuantity
from chemunited_sim.recorder.schema import create_all_tables

from chemunited.simulation.final_state import (
    _apply_discrete_state,
    _apply_edge_content,
    _apply_internal_edge_content,
    _apply_inventories,
    _build_inventory_payload,
    _latest_time,
    apply_final_simulation_state,
    apply_simulation_state_at,
    list_recorded_times,
    load_edge_cells,
)


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


class _FakeEdgeData:
    def __init__(self, diameter_value: float) -> None:
        self.diameter_value = diameter_value
        self.content: list = []


class _FakeConnection:
    """Duck-typed stand-in for a HydraulicConnectionItem: exposes .inf and .update()."""

    def __init__(self, diameter_value: float) -> None:
        self.inf = _FakeEdgeData(diameter_value)
        self.update_calls = 0

    def update(self) -> None:
        self.update_calls += 1


class _FakeConnections:
    def __init__(self, hydraulic: dict) -> None:
        self.hydraulic = hydraulic


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    create_all_tables(conn)
    return conn


def test_latest_time_returns_max_and_none_when_empty(tmp_path: Path) -> None:
    conn = _connect(tmp_path / "sim.db")
    assert _latest_time(conn) is None

    conn.execute(
        "INSERT INTO node_pressure (time, node_id, pressure) VALUES (?, ?, ?)",
        (1.0, "flask1.1", 101325.0),
    )
    conn.execute(
        "INSERT INTO node_pressure (time, node_id, pressure) VALUES (?, ?, ?)",
        (2.5, "flask1.1", 101325.0),
    )
    conn.commit()

    assert _latest_time(conn) == 2.5


def test_list_recorded_times_returns_sorted_distinct_times(tmp_path: Path) -> None:
    conn = _connect(tmp_path / "sim.db")
    conn.executemany(
        "INSERT INTO node_pressure (time, node_id, pressure) VALUES (?, ?, ?)",
        [
            (2.0, "a.1", 101325.0),
            (0.0, "a.1", 101325.0),
            (1.0, "a.1", 101325.0),
            (1.0, "b.1", 101325.0),  # duplicate time, different node
        ],
    )
    conn.commit()

    assert list_recorded_times(conn) == [0.0, 1.0, 2.0]


def test_list_recorded_times_returns_empty_list_when_no_rows(tmp_path: Path) -> None:
    conn = _connect(tmp_path / "sim.db")
    assert list_recorded_times(conn) == []


def test_build_inventory_payload_groups_by_component_and_skips_carrier(
    tmp_path: Path,
) -> None:
    conn = _connect(tmp_path / "sim.db")
    rows = [
        (1.0, "flask1.Inventory", "liquid", "red_dye", 0.002, 5e-6),
        (1.0, "flask1.Inventory", "gas", "__carrier__", 0.0, 4e-6),
        (1.0, "vial1.A1", "liquid", "blue_dye", 0.001, 2e-6),
        (0.5, "flask1.Inventory", "liquid", "green_dye", 0.999, 9e-6),
    ]
    conn.executemany(
        "INSERT INTO inventory_content "
        "(time, node_id, phase, species_id, moles, volume) VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()

    payload = _build_inventory_payload(conn, 1.0)

    assert set(payload) == {"flask1", "vial1"}
    assert payload["flask1"]["Inventory"]["liquid"] == {
        "volume": 5e-6,
        "initial_species": {"red_dye": 0.002},
    }
    # carrier species contributes its volume but never appears in initial_species
    assert payload["flask1"]["Inventory"]["gas"] == {
        "volume": 4e-6,
        "initial_species": {},
    }
    assert payload["vial1"]["A1"]["liquid"] == {
        "volume": 2e-6,
        "initial_species": {"blue_dye": 0.001},
    }


def test_load_edge_cells_orders_destination_first_with_species(
    tmp_path: Path,
) -> None:
    conn = _connect(tmp_path / "sim.db")
    conn.executemany(
        "INSERT INTO edge_cells (edge_id, cell_index, position_m, length_m) "
        "VALUES (?, ?, ?, ?)",
        [
            ("e1", 0, 0.0, 0.01),  # origin end
            ("e1", 1, 0.01, 0.01),  # destination end
        ],
    )
    conn.executemany(
        "INSERT INTO cell_state "
        "(time, edge_id, cell_index, phase, phase_fraction, temperature) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [
            (1.0, "e1", 0, "liquid", 1.0, 298.15),
            (1.0, "e1", 1, "gas", 1.0, 300.0),
        ],
    )
    conn.execute(
        "INSERT INTO cell_content "
        "(time, edge_id, cell_index, phase, species_id, moles) VALUES (?, ?, ?, ?, ?, ?)",
        (1.0, "e1", 0, "liquid", "red_dye", 0.001),
    )
    conn.commit()

    cells = load_edge_cells(conn, "e1", 1.0)

    assert set(cells) == {0, 1}
    origin_phase, origin_fraction, _, origin_length, origin_species = cells[0][0]
    assert origin_phase == PhaseKind.LIQUID
    assert origin_fraction == 1.0
    assert origin_length == 0.01
    assert origin_species == {"red_dye": 0.001}

    dest_phase, _, dest_temperature, _, dest_species = cells[1][0]
    assert dest_phase == PhaseKind.GAS
    assert dest_temperature == 300.0
    assert dest_species == {}

    # unknown/missing edge -> no static geometry -> None (distinct from a
    # known-but-empty-at-t edge, which returns {})
    assert load_edge_cells(conn, "missing", 1.0) is None


def test_apply_edge_content_builds_destination_first_volume_weighted_slugs(
    tmp_path: Path,
) -> None:
    conn = _connect(tmp_path / "sim.db")
    conn.executemany(
        "INSERT INTO edge_cells (edge_id, cell_index, position_m, length_m) "
        "VALUES (?, ?, ?, ?)",
        [
            ("e1", 0, 0.0, 0.01),  # origin, shorter cell
            ("e1", 1, 0.01, 0.03),  # destination, longer cell
        ],
    )
    conn.executemany(
        "INSERT INTO cell_state "
        "(time, edge_id, cell_index, phase, phase_fraction, temperature) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [
            (1.0, "e1", 0, "liquid", 1.0, 298.15),
            (1.0, "e1", 1, "liquid", 1.0, 298.15),
        ],
    )
    conn.commit()

    diameter = 0.001  # 1 mm
    connection = _FakeConnection(diameter_value=diameter)
    connections = _FakeConnections({"e1": connection})

    _apply_edge_content(conn, 1.0, connections)

    assert connection.update_calls == 1
    content = connection.inf.content
    assert len(content) == 2

    import math

    area = math.pi * (diameter / 2.0) ** 2
    origin_volume = 1.0 * 0.01 * area
    destination_volume = 1.0 * 0.03 * area
    # content[0] must be the destination-side slug (highest cell_index = 1, the longer cell)
    assert content[0].volume == destination_volume
    assert content[1].volume == origin_volume


def test_apply_edge_content_skips_edge_with_no_snapshot_rows(tmp_path: Path) -> None:
    conn = _connect(tmp_path / "sim.db")
    conn.commit()

    connection = _FakeConnection(diameter_value=0.001)
    connection.inf.content = ["untouched"]
    connections = _FakeConnections({"e1": connection})

    _apply_edge_content(conn, 1.0, connections)

    assert connection.update_calls == 0
    assert connection.inf.content == ["untouched"]


def test_apply_edge_content_clears_content_for_known_edge_empty_at_time(
    tmp_path: Path,
) -> None:
    """The recorder omits cell_state/cell_content rows entirely for a tube
    whose pocket queue is empty at a tick - a known edge with zero recorded
    content at *t* must clear stale content, not leave it untouched (that
    would only be correct for a genuinely unknown edge)."""
    conn = _connect(tmp_path / "sim.db")
    conn.executemany(
        "INSERT INTO edge_cells (edge_id, cell_index, position_m, length_m) "
        "VALUES (?, ?, ?, ?)",
        [("e1", 0, 0.0, 0.01)],
    )
    conn.commit()
    # no cell_state/cell_content rows at all -> edge known but empty at t=1.0

    connection = _FakeConnection(diameter_value=0.001)
    connection.inf.content = ["stale"]
    connections = _FakeConnections({"e1": connection})

    _apply_edge_content(conn, 1.0, connections)

    assert connection.update_calls == 1
    assert connection.inf.content == []


def test_apply_internal_edge_content_updates_plugflow_component_data(
    tmp_path: Path,
) -> None:
    """Loop/FlowReactor's own internal tube (edge id '<name>.1.2') is recorded
    in the same tables as external edges but never runs through a
    HydraulicConnectionItem - the content must land straight on the
    component's own data instead, and trigger a visual sync."""
    conn = _connect(tmp_path / "sim.db")
    conn.executemany(
        "INSERT INTO edge_cells (edge_id, cell_index, position_m, length_m) "
        "VALUES (?, ?, ?, ?)",
        [("Loop1.1.2", 0, 0.0, 0.01)],
    )
    conn.executemany(
        "INSERT INTO cell_state "
        "(time, edge_id, cell_index, phase, phase_fraction, temperature) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [(1.0, "Loop1.1.2", 0, "liquid", 1.0, 298.15)],
    )
    conn.execute(
        "INSERT INTO cell_content "
        "(time, edge_id, cell_index, phase, species_id, moles) VALUES (?, ?, ?, ?, ?, ?)",
        (1.0, "Loop1.1.2", 0, "liquid", "red_dye", 0.001),
    )
    conn.commit()

    loop = PlugFlowComponentData(name="Loop1", diameter=qty("1 mm"))
    component = _FakeComponent(inf=loop)

    _apply_internal_edge_content(conn, 1.0, {"Loop1": component})

    assert component.sync_calls == 1
    assert len(loop.content) == 1
    assert loop.content[0].initial_species == {"red_dye": 0.001}


def test_apply_internal_edge_content_skips_edge_with_no_snapshot_rows(
    tmp_path: Path,
) -> None:
    conn = _connect(tmp_path / "sim.db")
    conn.commit()

    loop = PlugFlowComponentData(name="Loop1")
    loop.content = ["untouched"]  # type: ignore[list-item]
    component = _FakeComponent(inf=loop)

    _apply_internal_edge_content(conn, 1.0, {"Loop1": component})

    assert component.sync_calls == 0
    assert loop.content == ["untouched"]


def test_apply_internal_edge_content_ignores_non_plugflow_components(
    tmp_path: Path,
) -> None:
    conn = _connect(tmp_path / "sim.db")
    conn.commit()

    vessel = VesselComponentData.from_mode(
        VesselMode(name="flask1", capacity=qty("10 ml"), top_access=1, bottom_access=1)
    )
    component = _FakeComponent(inf=vessel)

    _apply_internal_edge_content(conn, 1.0, {"flask1": component})  # must not raise

    assert component.sync_calls == 0


def test_apply_discrete_state_restores_rotor_ports_not_latest(tmp_path: Path) -> None:
    conn = _connect(tmp_path / "sim.db")
    conn.executemany(
        "INSERT INTO component_state (time, component, state) VALUES (?, ?, ?)",
        [
            (1.0, "Valve1", '{"rotor_ports": [[0, 1, null, null, null, null], [0]]}'),
            (2.0, "Valve1", '{"rotor_ports": [[0, null, 2, null, null, null], [0]]}'),
        ],
    )
    conn.commit()

    valve = RotaryValveData(name="Valve1")
    component = _FakeComponent(inf=valve)

    _apply_discrete_state(conn, 1.0, {"Valve1": component})

    assert valve.rotor_ports == [(0, 1, None, None, None, None), (0,)]
    assert component.sync_calls == 1


def test_apply_discrete_state_restores_solenoid_opened(tmp_path: Path) -> None:
    conn = _connect(tmp_path / "sim.db")
    conn.execute(
        "INSERT INTO component_state (time, component, state) VALUES (?, ?, ?)",
        (1.0, "Sol1", '{"opened": false}'),
    )
    conn.commit()

    solenoid = SolenoidValveData(name="Sol1")
    assert (
        solenoid.opened is True
    )  # default, sanity-check the restore actually flips it
    component = _FakeComponent(inf=solenoid)

    _apply_discrete_state(conn, 1.0, {"Sol1": component})

    assert solenoid.opened is False
    assert component.sync_calls == 1


def test_apply_discrete_state_restores_solenoid_2way_opened(tmp_path: Path) -> None:
    conn = _connect(tmp_path / "sim.db")
    conn.execute(
        "INSERT INTO component_state (time, component, state) VALUES (?, ?, ?)",
        (1.0, "Sol2", '{"opened": false}'),
    )
    conn.commit()

    solenoid = SolenoidValve2WayData(name="Sol2")
    component = _FakeComponent(inf=solenoid)

    _apply_discrete_state(conn, 1.0, {"Sol2": component})

    assert solenoid.opened is False
    assert component.sync_calls == 1


def test_apply_discrete_state_missing_table_is_noop(tmp_path: Path) -> None:
    conn = _connect(tmp_path / "sim.db")
    conn.execute("DROP TABLE component_state")
    conn.commit()

    valve = RotaryValveData(name="Valve1")
    component = _FakeComponent(inf=valve)

    _apply_discrete_state(conn, 1.0, {"Valve1": component})  # must not raise

    assert component.sync_calls == 0


def test_apply_inventories_updates_real_vessel_component_data(tmp_path: Path) -> None:
    conn = _connect(tmp_path / "sim.db")
    conn.executemany(
        "INSERT INTO inventory_content "
        "(time, node_id, phase, species_id, moles, volume) VALUES (?, ?, ?, ?, ?, ?)",
        [
            (1.0, "flask1.Inventory", "liquid", "red_dye", 0.05, 5e-6),
            (1.0, "flask1.Inventory", "gas", "__carrier__", 0.0, 4e-6),
        ],
    )
    conn.commit()

    vessel = VesselComponentData.from_mode(
        VesselMode(name="flask1", capacity=qty("10 ml"), top_access=1, bottom_access=1)
    )
    component = _FakeComponent(inf=vessel)

    _apply_inventories(conn, 1.0, {"flask1": component})

    inventory = vessel.internal_inventories[DEFAULT_INVENTORY_KEY]
    assert inventory.liq_content.volume == 5e-6
    assert inventory.liq_content.initial_species == {"red_dye": 0.05}
    assert inventory.gas_content.volume == 4e-6
    # the DB's untracked "__carrier__" gas is deliberately dropped from the
    # payload's species dict; apply_inventory_status_payload's ensure_air_defaults
    # then seeds it with "air" so the gas phase still renders a color.
    assert set(inventory.gas_content.initial_species) == {"air"}
    assert component.sync_calls == 1


def test_apply_final_simulation_state_end_to_end(tmp_path: Path) -> None:
    db_path = tmp_path / "sim.db"
    conn = _connect(db_path)
    conn.executemany(
        "INSERT INTO node_pressure (time, node_id, pressure) VALUES (?, ?, ?)",
        [(1.0, "flask1.1", 101325.0), (2.0, "flask1.1", 101325.0)],
    )
    conn.executemany(
        "INSERT INTO inventory_content "
        "(time, node_id, phase, species_id, moles, volume) VALUES (?, ?, ?, ?, ?, ?)",
        [
            (1.0, "flask1.Inventory", "liquid", "red_dye", 0.01, 1e-6),
            (2.0, "flask1.Inventory", "liquid", "red_dye", 0.05, 5e-6),
        ],
    )
    conn.executemany(
        "INSERT INTO edge_cells (edge_id, cell_index, position_m, length_m) "
        "VALUES (?, ?, ?, ?)",
        [("e1", 0, 0.0, 0.01)],
    )
    conn.executemany(
        "INSERT INTO cell_state "
        "(time, edge_id, cell_index, phase, phase_fraction, temperature) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [(2.0, "e1", 0, "liquid", 1.0, 298.15)],
    )
    conn.commit()
    conn.close()

    vessel = VesselComponentData.from_mode(
        VesselMode(name="flask1", capacity=qty("10 ml"), top_access=1, bottom_access=1)
    )
    component = _FakeComponent(inf=vessel)
    connection = _FakeConnection(diameter_value=0.001)

    apply_final_simulation_state(
        {"flask1": component}, _FakeConnections({"e1": connection}), db_path
    )

    # Only the t=2.0 (last) rows should be applied, not the t=1.0 rows.
    inventory = vessel.internal_inventories[DEFAULT_INVENTORY_KEY]
    assert inventory.liq_content.initial_species == {"red_dye": 0.05}
    assert connection.update_calls == 1
    assert len(connection.inf.content) == 1


def test_apply_simulation_state_at_applies_requested_time_not_latest(
    tmp_path: Path,
) -> None:
    conn = _connect(tmp_path / "sim.db")
    conn.executemany(
        "INSERT INTO inventory_content "
        "(time, node_id, phase, species_id, moles, volume) VALUES (?, ?, ?, ?, ?, ?)",
        [
            (1.0, "flask1.Inventory", "liquid", "red_dye", 0.01, 1e-6),
            (2.0, "flask1.Inventory", "liquid", "red_dye", 0.05, 5e-6),
        ],
    )
    conn.commit()

    vessel = VesselComponentData.from_mode(
        VesselMode(name="flask1", capacity=qty("10 ml"), top_access=1, bottom_access=1)
    )
    component = _FakeComponent(inf=vessel)

    apply_simulation_state_at(conn, 1.0, {"flask1": component}, _FakeConnections({}))

    inventory = vessel.internal_inventories[DEFAULT_INVENTORY_KEY]
    assert inventory.liq_content.initial_species == {"red_dye": 0.01}


def test_apply_final_simulation_state_handles_missing_db_gracefully(
    tmp_path: Path,
) -> None:
    apply_final_simulation_state(
        {}, _FakeConnections({}), tmp_path / "does_not_exist.db"
    )
