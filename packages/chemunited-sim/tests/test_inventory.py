"""Tests for inventory emission behavior."""

from __future__ import annotations

import math

import pytest
from chemunited_core.common.enums import ConnectionType, PhaseKind
from chemunited_core.components.enums import PortAccess
from chemunited_core.compounds import COMPOUNDS
from chemunited_core.compounds.entity import IDEAL_GAS_CONSTANT
from chemunited_core.connections import EdgeData, EdgeMode
from chemunited_core.figure_registry import COMPONENTS

from chemunited_sim.adapter import compile_graph
from chemunited_sim.hydraulics.models import HydraulicState
from chemunited_sim.inventory.engine import (
    HeatExchangeEntry,
    apply_heat_exchange,
    assimilate,
    emit,
)
from chemunited_sim.inventory.models import InventoryState
from chemunited_sim.inventory.port_map import EdgePortAccess, build_port_map
from chemunited_sim.transport.models import Pocket


def _state() -> InventoryState:
    return InventoryState(
        node_id="vessel.Inventory",
        capacity=1.0e-6,
        pressure=120_000.0,
        temperature=300.0,
        liq_volume=5.0e-7,
        gas_volume=5.0e-7,
        liq_species_moles={"solvent": 8.0},
        gas_species_moles={"nitrogen": 6.0},
    )


def test_emit_top_falls_back_to_liquid_when_gas_is_unavailable():
    state = _state()
    state.liq_volume = state.capacity
    state.gas_volume = 0.0
    emitted = emit(
        {"vessel.Inventory": state},
        {"edge": 3.0e-9},
        {"edge": EdgePortAccess("vessel.Inventory", PortAccess.TOP)},
    )

    pocket = emitted["edge"]
    assert pocket.phase_kind == PhaseKind.LIQUID
    assert pocket.volume == pytest.approx(3.0e-9)
    assert pocket.species_moles == {"solvent": pytest.approx(0.024)}
    assert state.gas_volume == pytest.approx(3.0e-9)
    assert state.gas_species_moles["nitrogen"] == pytest.approx(6.0)
    assert state.liq_volume == pytest.approx(state.capacity - 3.0e-9)
    assert state.liq_species_moles["solvent"] == pytest.approx(7.976)
    assert state.liq_volume + state.gas_volume == pytest.approx(state.capacity)


def test_emit_bottom_falls_back_to_gas_when_liquid_is_unavailable():
    state = _state()
    state.liq_volume = 0.0
    state.gas_volume = state.capacity
    emitted = emit(
        {"vessel.Inventory": state},
        {"edge": 4.0e-9},
        {"edge": EdgePortAccess("vessel.Inventory", PortAccess.BOTTOM)},
    )

    pocket = emitted["edge"]
    assert pocket.phase_kind == PhaseKind.GAS
    assert pocket.volume == pytest.approx(4.0e-9)
    assert pocket.species_moles == {"nitrogen": pytest.approx(0.024)}
    assert state.liq_volume == pytest.approx(0.0)
    assert state.liq_species_moles["solvent"] == pytest.approx(8.0)
    assert state.gas_volume == pytest.approx(state.capacity)
    assert state.gas_species_moles["nitrogen"] == pytest.approx(5.976)
    assert state.gas_species_moles["air"] == pytest.approx(
        state.pressure * 4.0e-9 / (IDEAL_GAS_CONSTANT * state.temperature)
    )
    assert state.liq_volume + state.gas_volume == pytest.approx(state.capacity)


def test_emit_sufficient_inventory_preserves_existing_fractional_behavior():
    state = _state()
    state.gas_volume = 2.0e-9
    state.liq_volume = state.capacity - state.gas_volume
    emitted = emit(
        {"vessel.Inventory": state},
        {"edge": 1.0e-9},
        {"edge": EdgePortAccess("vessel.Inventory", PortAccess.TOP)},
    )

    pocket = emitted["edge"]
    assert pocket.phase_kind == PhaseKind.GAS
    assert pocket.volume == pytest.approx(1.0e-9)
    assert pocket.species_moles == {"nitrogen": pytest.approx(3.0)}
    assert state.gas_volume == pytest.approx(2.0e-9)
    assert state.gas_species_moles["nitrogen"] == pytest.approx(3.0)
    assert state.gas_species_moles["air"] == pytest.approx(
        state.pressure * 1.0e-9 / (IDEAL_GAS_CONSTANT * state.temperature)
    )
    assert state.liq_volume + state.gas_volume == pytest.approx(state.capacity)


def test_emit_uses_carrier_only_when_both_phases_are_insufficient():
    state = _state()
    state.gas_volume = 1.0e-9
    state.liq_volume = 2.0e-9
    emitted = emit(
        {"vessel.Inventory": state},
        {"edge": 3.0e-9},
        {"edge": EdgePortAccess("vessel.Inventory", PortAccess.TOP)},
        variable_volume_inventory_ids={"vessel.Inventory"},
    )

    pocket = emitted["edge"]
    expected_air = state.pressure * 2.0e-9 / (IDEAL_GAS_CONSTANT * state.temperature)
    assert pocket.phase_kind == PhaseKind.GAS
    assert pocket.volume == pytest.approx(3.0e-9)
    assert pocket.species_moles["nitrogen"] == pytest.approx(6.0)
    assert pocket.species_moles["air"] == pytest.approx(expected_air)
    assert state.gas_volume == pytest.approx(0.0)
    assert state.liq_volume == pytest.approx(2.0e-9)
    assert state.gas_species_moles["nitrogen"] == pytest.approx(0.0)


def test_normal_vessel_liquid_assimilation_displaces_headspace():
    state = _state()

    assimilate(
        {"vessel.Inventory": state},
        {
            "vessel.Inventory": [
                Pocket(
                    phase_kind=PhaseKind.LIQUID,
                    volume=1.0e-7,
                    species_moles={"solute": 2.0},
                    temperature=300.0,
                    pressure=120_000.0,
                )
            ]
        },
        HydraulicState(pressures={"vessel.Inventory": 120_000.0}, flows={}),
    )

    assert state.liq_volume == pytest.approx(6.0e-7)
    assert state.gas_volume == pytest.approx(4.0e-7)
    assert state.liq_species_moles["solute"] == pytest.approx(2.0)
    assert state.liq_volume + state.gas_volume == pytest.approx(state.capacity)


def test_variable_volume_inventory_can_grow_on_assimilation():
    state = _state()

    assimilate(
        {"vessel.Inventory": state},
        {
            "vessel.Inventory": [
                Pocket(
                    phase_kind=PhaseKind.LIQUID,
                    volume=1.0e-7,
                    species_moles={"solute": 2.0},
                    temperature=300.0,
                    pressure=120_000.0,
                )
            ]
        },
        HydraulicState(pressures={"vessel.Inventory": 120_000.0}, flows={}),
        variable_volume_inventory_ids={"vessel.Inventory"},
    )

    assert state.liq_volume == pytest.approx(6.0e-7)
    assert state.gas_volume == pytest.approx(5.0e-7)
    assert state.liq_volume + state.gas_volume == pytest.approx(state.capacity + 1.0e-7)


def test_autosampler_transport_edge_emits_liquid_from_selected_vial():
    gantry_defn = COMPONENTS["Gantry3D"]
    vial_defn = COMPONENTS["Vial"]
    sink_defn = COMPONENTS["PressureControl"]
    gantry = gantry_defn.data_class.from_mode(
        gantry_defn.mode_class(
            name="as", position_x="1", position_y="A", position_z="DOWN"
        )
    )
    vial = vial_defn.data_class.from_mode(
        vial_defn.mode_class(name="tray", column=3, row=2, pressure_access=False)
    )
    sink = sink_defn.data_class.from_mode(sink_defn.mode_class(name="sink"))
    contact = EdgeData.from_mode(
        EdgeMode(
            name="tray_1_as_2",
            origin="tray",
            origin_port=1,
            destination="as",
            destination_port=2,
            classification=ConnectionType.MOVEMENT,
        )
    )
    outlet = EdgeData.from_mode(
        EdgeMode(
            name="as_1_sink_1",
            origin="as",
            origin_port=1,
            destination="sink",
            destination_port=1,
            classification=ConnectionType.HYDRAULIC,
            length="100 mm",
            diameter="1 mm",
        )
    )
    graph = compile_graph([gantry, vial, sink], [contact, outlet])

    port_map = build_port_map(graph, [gantry, vial, sink])

    assert port_map["as_1_sink_1"] == EdgePortAccess("tray.A1", PortAccess.BOTTOM)

    state = InventoryState(
        node_id="tray.A1",
        capacity=1.0e-6,
        pressure=101_325.0,
        temperature=300.0,
        liq_volume=1.0e-6,
        gas_volume=0.0,
        liq_species_moles={"HeavyWater": 1.0},
        gas_species_moles={},
    )
    emitted = emit(
        {"tray.A1": state},
        {"as_1_sink_1": 1.0e-9},
        port_map,
    )

    pocket = emitted["as_1_sink_1"]
    assert pocket.phase_kind == PhaseKind.LIQUID
    assert pocket.species_moles == {"HeavyWater": pytest.approx(1.0e-3)}
    assert state.liq_volume == pytest.approx(9.99e-7)
    assert state.liq_species_moles["HeavyWater"] == pytest.approx(0.999)


def test_apply_heat_exchange_matches_closed_form_solution():
    state = InventoryState(
        node_id="vessel.Inventory",
        capacity=1.0e-6,
        pressure=101_325.0,
        temperature=298.15,
        liq_volume=5.0e-7,
        gas_volume=5.0e-7,
        liq_species_moles={},
        gas_species_moles={"air": 1.0e-2},
    )
    entry = HeatExchangeEntry(
        inv_node_id="vessel.Inventory",
        U=50.0,
        contact_area=0.01,
        T_wall=313.15,
    )

    apply_heat_exchange({"vessel.Inventory": state}, [entry], dt=2.0)

    c_thermal = (
        state.gas_species_moles["air"]
        * COMPOUNDS["air"].cp("gas").to_base_units().magnitude
    )
    expected = entry.T_wall + (298.15 - entry.T_wall) * math.exp(
        -(entry.U * entry.contact_area * 2.0) / c_thermal
    )
    assert state.temperature == pytest.approx(expected)


def test_apply_heat_exchange_remains_stable_for_near_zero_thermal_mass():
    """Regression test: a forward-Euler update diverges to +/-inf and NaN for a
    vanishingly small but nonzero thermal mass; the closed-form update must stay
    bounded between the initial temperature and the wall temperature instead.
    """
    state = InventoryState(
        node_id="vessel.Inventory",
        capacity=1.0e-6,
        pressure=101_325.0,
        temperature=298.15,
        liq_volume=5.0e-7,
        gas_volume=5.0e-7,
        liq_species_moles={},
        gas_species_moles={"air": 1.0e-10},
    )
    entry = HeatExchangeEntry(
        inv_node_id="vessel.Inventory",
        U=50.0,
        contact_area=0.01,
        T_wall=313.15,
    )

    for _ in range(20):
        apply_heat_exchange({"vessel.Inventory": state}, [entry], dt=2.0)
        assert math.isfinite(state.temperature)
        assert 298.15 <= state.temperature <= 313.15

    assert state.temperature == pytest.approx(313.15, abs=1e-6)
