"""Tests for the worker module.

Covers:
- Import smoke test
- SimConfig construction
- Worker initial state (t=0, hyd_state=None)
- step(): advances t, sets hyd_state
- run(): advances t to t_end, closes recorder
- Recorder integration: correct times written to SQLite
- BPR stabilisation: opens when P_upstream >= setpoint, stays closed otherwise
"""

from __future__ import annotations

import sqlite3
from collections import deque

import pytest
from chemunited_core.common.constant import R_MAX_HYDRAULIC
from chemunited_core.common.enums import ConnectionType, PhaseKind
from chemunited_core.components import (
    BackPressureRegulatorData,
    BackPressureRegulatorMode,
    PlugFlowComponentData,
    PlugFlowMode,
    PressureControlData,
    PressureControlMode,
)
from chemunited_core.connections import EdgeData, EdgeMode
from chemunited_core.figure_registry import COMPONENTS
from chemunited_quantities import ChemUnitQuantity

from chemunited_sim.adapter import compile_graph, resync_component
from chemunited_sim.reactions import FirstOrderDecay
from chemunited_sim.recorder import Recorder
from chemunited_sim.transport.models import Pocket
from chemunited_sim.worker import SimConfig, Worker

# ---------------------------------------------------------------------------
# Fixtures — minimal platform builder
# ---------------------------------------------------------------------------


def _make_tube_platform(
    src_bar: float = 2.0,
    snk_bar: float = 1.0,
    tube_length_cm: float = 10.0,
    tube_dia_mm: float = 4.0,
):
    """Two pressure controllers connected by a PlugFlow tube.

    src (src_bar) → e_in → tube → e_out → snk (snk_bar)

    No vessel, no BPR — the simplest possible hydraulic network.
    """
    src = PressureControlData.from_mode(
        PressureControlMode(name="src", setpoint=ChemUnitQuantity(f"{src_bar} bar"))
    )
    tube = PlugFlowComponentData.from_mode(
        PlugFlowMode(
            name="tube",
            length=ChemUnitQuantity(f"{tube_length_cm} cm"),
            diameter=ChemUnitQuantity(f"{tube_dia_mm} mm"),
        )
    )
    snk = PressureControlData.from_mode(
        PressureControlMode(name="snk", setpoint=ChemUnitQuantity(f"{snk_bar} bar"))
    )
    e_in = EdgeData.from_mode(
        EdgeMode(
            name="ein",
            origin="src",
            origin_port=1,
            destination="tube",
            destination_port=1,
            classification=ConnectionType.HYDRAULIC,
            length=ChemUnitQuantity("5 cm"),
            diameter=ChemUnitQuantity("4 mm"),
        )
    )
    e_out = EdgeData.from_mode(
        EdgeMode(
            name="eout",
            origin="tube",
            origin_port=2,
            destination="snk",
            destination_port=1,
            classification=ConnectionType.HYDRAULIC,
            length=ChemUnitQuantity("5 cm"),
            diameter=ChemUnitQuantity("4 mm"),
        )
    )
    components = [src, tube, snk]
    graph = compile_graph(components, [e_in, e_out])
    return graph, components


def _make_bpr_platform(setpoint_bar: float = 1.2):
    """src (3 bar) → tube → BPR → snk (1 bar).

    Setpoint choices:
      1.2 bar → BPR opens  (P_upstream-open ≈ 1.4 bar > 1.2 bar → stable open)
      3.5 bar → BPR stays closed (P_upstream-closed ≈ 3 bar < 3.5 bar → stable closed)
    """
    src = PressureControlData.from_mode(
        PressureControlMode(name="src", setpoint=ChemUnitQuantity("3 bar"))
    )
    tube = PlugFlowComponentData.from_mode(
        PlugFlowMode(
            name="tube",
            length=ChemUnitQuantity("10 cm"),
            diameter=ChemUnitQuantity("4 mm"),
        )
    )
    bpr = BackPressureRegulatorData.from_mode(
        BackPressureRegulatorMode(
            name="bpr",
            setpoint=ChemUnitQuantity(f"{setpoint_bar} bar"),
        )
    )
    snk = PressureControlData.from_mode(
        PressureControlMode(name="snk", setpoint=ChemUnitQuantity("1 bar"))
    )
    e1 = EdgeData.from_mode(
        EdgeMode(
            name="e1",
            origin="src",
            origin_port=1,
            destination="tube",
            destination_port=1,
            classification=ConnectionType.HYDRAULIC,
            length=ChemUnitQuantity("5 cm"),
            diameter=ChemUnitQuantity("4 mm"),
        )
    )
    e2 = EdgeData.from_mode(
        EdgeMode(
            name="e2",
            origin="tube",
            origin_port=2,
            destination="bpr",
            destination_port=1,
            classification=ConnectionType.HYDRAULIC,
            length=ChemUnitQuantity("5 cm"),
            diameter=ChemUnitQuantity("4 mm"),
        )
    )
    e3 = EdgeData.from_mode(
        EdgeMode(
            name="e3",
            origin="bpr",
            origin_port=2,
            destination="snk",
            destination_port=1,
            classification=ConnectionType.HYDRAULIC,
            length=ChemUnitQuantity("5 cm"),
            diameter=ChemUnitQuantity("4 mm"),
        )
    )
    components = [src, tube, bpr, snk]
    graph = compile_graph(components, [e1, e2, e3])
    return graph, components


def _make_mfc_platform(src_bar: float = 5.0, snk_bar: float = 1.0):
    """src (src_bar) -- MFC -- snk (snk_bar). No tube in between other than
    the MFC's own port wiring, so once the MFC's resistance is calibrated to
    its setpoint, the solved flow through it should sit close to that
    setpoint regardless of the (fixed) src/snk pressure differential.
    """
    src = PressureControlData.from_mode(
        PressureControlMode(name="src", setpoint=ChemUnitQuantity(f"{src_bar} bar"))
    )
    mfc_defn = COMPONENTS["MFCComponent"]
    mfc = mfc_defn.data_class.from_mode(mfc_defn.mode_class(name="mfc"))
    snk = PressureControlData.from_mode(
        PressureControlMode(name="snk", setpoint=ChemUnitQuantity(f"{snk_bar} bar"))
    )
    e_in = EdgeData.from_mode(
        EdgeMode(
            name="ein",
            origin="src",
            origin_port=1,
            destination="mfc",
            destination_port=1,
            classification=ConnectionType.HYDRAULIC,
            length=ChemUnitQuantity("5 cm"),
            diameter=ChemUnitQuantity("4 mm"),
        )
    )
    e_out = EdgeData.from_mode(
        EdgeMode(
            name="eout",
            origin="mfc",
            origin_port=2,
            destination="snk",
            destination_port=1,
            classification=ConnectionType.HYDRAULIC,
            length=ChemUnitQuantity("5 cm"),
            diameter=ChemUnitQuantity("4 mm"),
        )
    )
    components = [src, mfc, snk]
    graph = compile_graph(components, [e_in, e_out])
    return graph, components, mfc


def _make_pump_platform(src_bar: float = 1.0, snk_bar: float = 5.0):
    """src (src_bar) -> HPLCPump -> snk (snk_bar).

    Defaults to genuine adverse back-pressure (snk_bar > src_bar) -- the
    scenario in which the old dp/Q resistance-matching iteration could settle
    on a wrong-signed (backward) flow for many ticks.
    """
    src = PressureControlData.from_mode(
        PressureControlMode(name="src", setpoint=ChemUnitQuantity(f"{src_bar} bar"))
    )
    pump_defn = COMPONENTS["HPLCPump"]
    pump = pump_defn.data_class.from_mode(pump_defn.mode_class(name="hplcpump"))
    snk = PressureControlData.from_mode(
        PressureControlMode(name="snk", setpoint=ChemUnitQuantity(f"{snk_bar} bar"))
    )
    e_in = EdgeData.from_mode(
        EdgeMode(
            name="ein",
            origin="src",
            origin_port=1,
            destination="hplcpump",
            destination_port=1,
            classification=ConnectionType.HYDRAULIC,
            length=ChemUnitQuantity("5 cm"),
            diameter=ChemUnitQuantity("4 mm"),
        )
    )
    e_out = EdgeData.from_mode(
        EdgeMode(
            name="eout",
            origin="hplcpump",
            origin_port=2,
            destination="snk",
            destination_port=1,
            classification=ConnectionType.HYDRAULIC,
            length=ChemUnitQuantity("5 cm"),
            diameter=ChemUnitQuantity("4 mm"),
        )
    )
    components = [src, pump, snk]
    graph = compile_graph(components, [e_in, e_out])
    return graph, components, pump


# ---------------------------------------------------------------------------
# 1. Import smoke test
# ---------------------------------------------------------------------------


def test_imports():
    assert Worker is not None
    assert SimConfig is not None


# ---------------------------------------------------------------------------
# 2. SimConfig
# ---------------------------------------------------------------------------


def test_simconfig_defaults():
    cfg = SimConfig(dt=0.1, t_end=10.0)
    assert cfg.dt == pytest.approx(0.1)
    assert cfg.t_end == pytest.approx(10.0)
    assert cfg.viscosity > 0.0


# ---------------------------------------------------------------------------
# 3. Worker initial state
# ---------------------------------------------------------------------------


def test_worker_initial_t():
    graph, components = _make_tube_platform()
    w = Worker(graph, components, SimConfig(dt=0.1, t_end=1.0))
    assert w.t == pytest.approx(0.0)


def test_worker_initial_hyd_state_is_none():
    graph, components = _make_tube_platform()
    w = Worker(graph, components, SimConfig(dt=0.1, t_end=1.0))
    assert w.hyd_state is None


def test_worker_initial_transport_state_has_queues():
    graph, components = _make_tube_platform()
    w = Worker(graph, components, SimConfig(dt=0.1, t_end=1.0))
    # At least one TRANSPORT edge should have a queue
    assert len(w.transport_state.edge_queues) > 0


def test_worker_reacts_resident_transport_pockets_before_advance():
    graph, components = _make_tube_platform(src_bar=1.0, snk_bar=1.0)
    reaction = FirstOrderDecay(
        reactant="a",
        product="b",
        rate_constant=0.5,
        phase=PhaseKind.LIQUID,
    )
    worker = Worker(
        graph,
        components,
        SimConfig(dt=1.0, t_end=1.0),
        reactions_map={"tube.1.2": [reaction]},
    )
    worker.transport_state.edge_queues["tube.1.2"] = deque(
        [
            Pocket(
                phase_kind=PhaseKind.LIQUID,
                volume=1.0e-6,
                species_moles={"a": 1.0},
                temperature=298.0,
                pressure=101_325.0,
            )
        ]
    )

    worker.step()

    pocket = worker.transport_state.edge_queues["tube.1.2"][0]
    assert pocket.species_moles == pytest.approx({"a": 0.5, "b": 0.5})


# ---------------------------------------------------------------------------
# 4. step()
# ---------------------------------------------------------------------------


def test_step_advances_t():
    graph, components = _make_tube_platform()
    cfg = SimConfig(dt=0.1, t_end=1.0)
    w = Worker(graph, components, cfg)
    w.step()
    assert w.t == pytest.approx(0.1)


def test_step_sets_hyd_state():
    graph, components = _make_tube_platform()
    w = Worker(graph, components, SimConfig(dt=0.1, t_end=1.0))
    w.step()
    assert w.hyd_state is not None
    assert "src.1" in w.hyd_state.pressures
    assert w.hyd_state.pressures["src.1"] == pytest.approx(200_000.0)


def test_step_flow_is_positive():
    """Flow from high to low pressure should be positive."""
    graph, components = _make_tube_platform(src_bar=2.0, snk_bar=1.0)
    w = Worker(graph, components, SimConfig(dt=0.1, t_end=1.0))
    w.step()
    flows = w.hyd_state.flows
    # All edges in this single-path network should have the same positive flow
    for flow in flows.values():
        assert flow > 0.0


def test_multiple_steps_accumulate_t():
    graph, components = _make_tube_platform()
    cfg = SimConfig(dt=0.1, t_end=1.0)
    w = Worker(graph, components, cfg)
    for _ in range(5):
        w.step()
    assert w.t == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# 5. run()
# ---------------------------------------------------------------------------


def test_run_advances_past_t_end():
    graph, components = _make_tube_platform()
    cfg = SimConfig(dt=0.1, t_end=1.0)
    w = Worker(graph, components, cfg)
    w.run()
    # run() steps until round(t/dt) > round(t_end/dt), so t > t_end
    assert w.t > cfg.t_end


def test_run_records_t_end_in_last_step():
    """t after run() should be exactly one dt past t_end."""
    graph, components = _make_tube_platform()
    cfg = SimConfig(dt=0.1, t_end=1.0)
    w = Worker(graph, components, cfg)
    w.run()
    assert w.t == pytest.approx(cfg.t_end + cfg.dt)


def test_run_closes_recorder(tmp_path):
    graph, components = _make_tube_platform()
    db = tmp_path / "run.db"
    rec = Recorder(db_path=db, graph=graph, dt=0.1, record_interval=1.0)
    cfg = SimConfig(dt=0.1, t_end=1.0)
    w = Worker(graph, components, cfg, recorder=rec)
    w.run()
    # After run(), connection is closed; opening for read should work
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    count = conn.execute("SELECT COUNT(*) FROM node_pressure").fetchone()[0]
    conn.close()
    assert count > 0


# ---------------------------------------------------------------------------
# 6. Recorder integration
# ---------------------------------------------------------------------------


def test_recorder_captures_t0(tmp_path):
    """Record at t=0 should be present because step() records BEFORE advancing."""
    graph, components = _make_tube_platform()
    db = tmp_path / "t0.db"
    rec = Recorder(db_path=db, graph=graph, dt=0.1, record_interval=1.0)
    cfg = SimConfig(dt=0.1, t_end=2.0)
    w = Worker(graph, components, cfg, recorder=rec)
    w.run()

    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    times = sorted(set(r[0] for r in conn.execute("SELECT time FROM node_pressure")))
    conn.close()

    assert 0.0 in times


def test_recorder_captures_correct_interval(tmp_path):
    """record_interval=1.0 with dt=0.1 should produce recordings at 0, 1, 2."""
    graph, components = _make_tube_platform()
    db = tmp_path / "interval.db"
    rec = Recorder(db_path=db, graph=graph, dt=0.1, record_interval=1.0)
    cfg = SimConfig(dt=0.1, t_end=2.0)
    w = Worker(graph, components, cfg, recorder=rec)
    w.run()

    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    times = sorted(set(r[0] for r in conn.execute("SELECT time FROM node_pressure")))
    conn.close()

    assert len(times) == 3  # t=0, 1, 2
    assert times[0] == pytest.approx(0.0)
    assert times[1] == pytest.approx(1.0, abs=1e-9)
    assert times[2] == pytest.approx(2.0, abs=1e-9)


def test_recorder_has_edge_flow_rows(tmp_path):
    graph, components = _make_tube_platform()
    db = tmp_path / "flow.db"
    rec = Recorder(db_path=db, graph=graph, dt=0.1, record_interval=1.0)
    cfg = SimConfig(dt=0.1, t_end=1.0)
    w = Worker(graph, components, cfg, recorder=rec)
    w.run()

    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    count = conn.execute("SELECT COUNT(*) FROM edge_flow").fetchone()[0]
    conn.close()
    assert count > 0


# ---------------------------------------------------------------------------
# 7. BPR stabilisation
# ---------------------------------------------------------------------------


def test_bpr_opens_when_upstream_exceeds_setpoint():
    """setpoint=1.2 bar: after one step BPR resistance should be < R_MAX."""
    graph, components = _make_bpr_platform(setpoint_bar=1.2)
    cfg = SimConfig(dt=0.1, t_end=0.1)
    w = Worker(graph, components, cfg)
    w.step()
    bpr_edge = graph.edges["bpr.1.2"]
    assert bpr_edge.resistance_override != pytest.approx(
        R_MAX_HYDRAULIC
    ), "BPR should open"


def test_bpr_stays_closed_when_upstream_below_setpoint():
    """setpoint=3.5 bar, src=3 bar: upstream < setpoint — BPR stays closed."""
    graph, components = _make_bpr_platform(setpoint_bar=3.5)
    cfg = SimConfig(dt=0.1, t_end=0.1)
    w = Worker(graph, components, cfg)
    w.step()
    bpr_edge = graph.edges["bpr.1.2"]
    assert bpr_edge.resistance_override == pytest.approx(R_MAX_HYDRAULIC)


def test_bpr_open_allows_flow():
    """When BPR opens, flow through the BPR edge is nonzero after convergence."""
    graph, components = _make_bpr_platform(setpoint_bar=1.2)
    cfg = SimConfig(dt=0.1, t_end=1.0)
    w = Worker(graph, components, cfg)
    w.run()
    assert abs(w.hyd_state.flows.get("bpr.1.2", 0.0)) > 1e-9


def test_bpr_closed_blocks_flow():
    """When BPR is closed (setpoint=3.5 bar), flow through BPR is near zero."""
    graph, components = _make_bpr_platform(setpoint_bar=3.5)
    cfg = SimConfig(dt=0.1, t_end=0.1)
    w = Worker(graph, components, cfg)
    w.step()
    assert abs(w.hyd_state.flows.get("bpr.1.2", 0.0)) < 1e-6


def test_bpr_never_carries_backward_flow_when_downstream_pressure_spikes():
    """Regression test: a BPR is a one-way check valve and must never carry
    flow backward, even after it has already opened, if something downstream
    later pushes pressure above upstream.
    """
    graph, components = _make_bpr_platform(setpoint_bar=1.2)
    comp_by_name = {c.name: c for c in components}
    cfg = SimConfig(dt=0.1, t_end=3.0)
    w = Worker(graph, components, cfg)

    # Let the BPR open normally (src=3 bar > setpoint=1.2 bar).
    for _ in range(5):
        w.step()
    assert graph.edges["bpr.1.2"].resistance_override != pytest.approx(R_MAX_HYDRAULIC)
    assert w.hyd_state.flows["bpr.1.2"] > 0.0

    # Push downstream pressure above upstream -- nothing should ever flow
    # from snk back through the BPR toward src, no matter how the BPR's own
    # open/close state reacts to it.
    snk = comp_by_name["snk"]
    snk.setpoint = ChemUnitQuantity("10 bar")
    snk.sync_internal_state()
    resync_component(graph, snk)

    for _ in range(20):
        w.step()
        assert w.hyd_state.flows["bpr.1.2"] >= 0.0


# ---------------------------------------------------------------------------
# 8. Pump forced flow against back-pressure (HPLCPump backward-flow regression)
# ---------------------------------------------------------------------------


def test_pump_forces_exact_flow_against_backpressure_from_first_step():
    """Regression test for the reported bug: a pump commanded to infuse
    against real back-pressure (downstream setpoint > upstream setpoint)
    must carry exactly the commanded flow, correctly signed, from the very
    first solved step -- never zero, and never backward, not even
    transiently.
    """
    graph, components, pump = _make_pump_platform(src_bar=1.0, snk_bar=5.0)
    pump.apply("infuse", rate="1 ml/min")
    resync_component(graph, pump)
    expected_flow_si = float(ChemUnitQuantity("1 ml/min").to_base_units().magnitude)

    cfg = SimConfig(dt=0.1, t_end=1.0)
    w = Worker(graph, components, cfg)

    for _ in range(10):
        w.step()
        assert w.hyd_state is not None
        assert w.hyd_state.flows["hplcpump.1.2"] == pytest.approx(expected_flow_si)


def test_pump_stop_closes_edge_and_stops_flow():
    graph, components, pump = _make_pump_platform(src_bar=1.0, snk_bar=5.0)
    pump.apply("infuse", rate="1 ml/min")
    resync_component(graph, pump)

    cfg = SimConfig(dt=0.1, t_end=0.2)
    w = Worker(graph, components, cfg)
    w.step()

    pump.apply("stop")
    resync_component(graph, pump)
    w.step()

    assert w.hyd_state is not None
    assert w.hyd_state.flows["hplcpump.1.2"] == pytest.approx(0.0, abs=1e-12)


# ---------------------------------------------------------------------------
# 9. MFC transient-resistance seeding (mid-run set-flow-rate regression)
# ---------------------------------------------------------------------------


def test_mfc_does_not_overshoot_setpoint_on_first_tick_after_midrun_command():
    """Regression test: an MFC commanded mid-run, after the sim already has a
    real prior pressure differential across it, must not transiently act as
    a near-short-circuit on the very first solved tick after
    `set-flow-rate`. Without seeding the edge's resistance from the last
    known pressures before that tick's solve, an open-but-uncalibrated
    JUNCTION edge falls back to R_JUNCTION (far below normal tube
    resistance), so with a real ~4 bar differential already present the
    solved flow would be orders of magnitude above the 5 ml/min setpoint.
    """
    graph, components, mfc = _make_mfc_platform(src_bar=5.0, snk_bar=1.0)
    cfg = SimConfig(dt=0.1, t_end=1.0)
    w = Worker(graph, components, cfg)

    # Let the still-closed MFC settle for a few ticks so a genuine ~4 bar dp
    # exists across it in the worker's last completed hyd_state.
    for _ in range(5):
        w.step()
    assert graph.edges["mfc.1.2"].resistance_override == pytest.approx(R_MAX_HYDRAULIC)

    mfc.apply("set-flow-rate", flowrate="5 ml/min")
    resync_component(graph, mfc)
    # Opens immediately on command -- this contract must not change.
    assert graph.edges["mfc.1.2"].resistance_override is None

    w.step()

    expected_flow_si = float(ChemUnitQuantity("5 ml/min").to_base_units().magnitude)
    actual_flow_si = w.hyd_state.flows["mfc.1.2"]
    assert actual_flow_si == pytest.approx(expected_flow_si, rel=0.1)


def test_worker_heat_connection_uses_live_controller_temperature():
    controller_defn = COMPONENTS["TemperatureControl"]
    vessel_defn = COMPONENTS["GlassBottle"]
    controller = controller_defn.data_class.from_mode(
        controller_defn.mode_class(name="chiller")
    )
    vessel = vessel_defn.data_class.from_mode(
        vessel_defn.mode_class(
            name="reactor",
            heat_exchange=True,
            heat_transfer_coefficient=ChemUnitQuantity("0.01 W/(m^2*K)"),
            surface_temperature=ChemUnitQuantity("350 K"),
        )
    )
    vessel.internal_inventory.gas_content.initial_species = {"air": 1.0e-5}
    heat_link = EdgeData.from_mode(
        EdgeMode(
            name="chiller_reactor_heat",
            origin="chiller",
            origin_port=1,
            destination="reactor",
            destination_port=2,
            classification=ConnectionType.HEAT,
        )
    )
    graph = compile_graph([controller, vessel], [heat_link])
    worker = Worker(graph, [controller, vessel], SimConfig(dt=0.1, t_end=0.1))

    controller.apply("set_temperature", temp=ChemUnitQuantity("10 C"))
    worker.step()

    assert worker.inv_states["reactor.Inventory"].temperature < 298.15
