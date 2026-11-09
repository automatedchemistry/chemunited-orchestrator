"""A step never moves more than a tube holds, and a vessel can drain to empty."""

from __future__ import annotations

import pytest
from loguru import logger

from chemunited_core.common.enums import ConnectionType, PhaseKind
from chemunited_core.connections import EdgeData, EdgeMode
from chemunited_core.figure_registry import COMPONENTS
from chemunited_quantities import ChemUnitQuantity
from chemunited_sim.adapter import compile_graph
from chemunited_sim.hydraulics.solver import solve
from chemunited_sim.transport.engine import edge_capacity
from chemunited_sim.worker import SimConfig, Worker

TUBE_M3 = 7.853981633974483e-08  # 100 mm x 1 mm
VISCOSITY = SimConfig().viscosity


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


def _set_flow(graph, edge_id: str, target_m3_s: float) -> None:
    """Fit one tube's resistance so that the line carries `target_m3_s`."""
    graph.edges[edge_id].resistance_override = 1.0e6
    first = solve(graph, VISCOSITY).flows[edge_id]
    graph.edges[edge_id].resistance_override = 2.0e6
    second = solve(graph, VISCOSITY).flows[edge_id]
    # Q = dP / (R + rest), so 1/Q is a straight line in R.
    slope = (1.0 / second - 1.0 / first) / 1.0e6
    intercept = 1.0 / first - slope * 1.0e6
    graph.edges[edge_id].resistance_override = (1.0 / target_m3_s - intercept) / slope


def _bottle_through_three_tubes(flow_ml_s: float, liquid_ml: float = 50.0):
    """Argon pushes a bottle's liquid through three tubes into a sealed vessel.

    The vessel vents through a fourth tube, so what arrives there is measurable.
    """
    argon = _make("Source", "argon", setpoint=ChemUnitQuantity("1.2 bar"))
    bottle = _make(
        "GlassBottle",
        "bottle",
        capacity=ChemUnitQuantity("100 ml"),
        top_access=1,
        bottom_access=1,
        pressure_access=True,
    )
    bottle.internal_inventory.liq_content.volume = liquid_ml * 1e-6
    bottle.internal_inventory.liq_content.initial_species = {"water": liquid_ml * 0.05}
    bottle.internal_inventory.gas_content.volume = (100.0 - liquid_ml) * 1e-6
    bottle.internal_inventory.gas_content.initial_species = {"air": 1.0e-3}
    middle = _make("Distributor", "middle", number_ports=3)
    receiver = _make(
        "GlassBottle",
        "receiver",
        capacity=ChemUnitQuantity("100 ml"),
        top_access=2,
        bottom_access=1,
        pressure_access=True,
    )
    receiver.internal_inventory.gas_content.volume = 100.0e-6
    receiver.internal_inventory.gas_content.initial_species = {"air": 4.0e-3}
    waste = _make("Sink", "waste")
    edges = [
        _tube("argon", 1, "bottle", 1),
        _tube("bottle", 2, "middle", 1),
        _tube("middle", 2, "receiver", 1),
        _tube("receiver", 2, "waste", 1),
    ]
    components = [argon, bottle, middle, receiver, waste]
    graph = compile_graph(components, edges)
    _set_flow(graph, "bottle_2_middle_1", flow_ml_s * 1e-6)
    return graph, components


def test_slow_flow_needs_no_substeps() -> None:
    graph, components = _bottle_through_three_tubes(flow_ml_s=0.5)
    worker = Worker(graph, components, SimConfig(dt=0.1))

    worker.step()

    assert worker._transport_substeps(worker.hyd_state) == 1


def test_fast_flow_is_cut_so_that_no_tube_is_overrun() -> None:
    graph, components = _bottle_through_three_tubes(flow_ml_s=3.0)
    worker = Worker(graph, components, SimConfig(dt=0.1))

    worker.step()

    # 300 uL in a step, through 78.5 uL tubes.
    assert worker._transport_substeps(worker.hyd_state) == 4


def test_exactly_one_tube_per_step_is_one_piece() -> None:
    graph, components = _bottle_through_three_tubes(flow_ml_s=0.5)
    edge = graph.edges["bottle_2_middle_1"]
    assert edge_capacity(edge) == pytest.approx(TUBE_M3)
    worker = Worker(graph, components, SimConfig(dt=0.1))
    worker.step()
    state = worker.hyd_state
    flow = TUBE_M3 / 0.1
    capped = type(state)(
        pressures=state.pressures,
        flows={edge_id: flow for edge_id in state.flows},
    )

    assert worker._transport_substeps(capped) == 1


def test_hitting_the_limit_warns_once_and_uses_the_limit() -> None:
    graph, components = _bottle_through_three_tubes(flow_ml_s=3.0)
    worker = Worker(graph, components, SimConfig(dt=0.1, max_transport_substeps=2))
    messages: list[str] = []
    sink = logger.add(lambda m: messages.append(m.record["message"]), level="WARNING")
    try:
        worker.step()
        needed = worker._transport_substeps(worker.hyd_state)
        worker.step()
    finally:
        logger.remove(sink)

    assert needed == 2
    assert len([m for m in messages if "max_transport_substeps" in m]) == 1


@pytest.mark.parametrize("flow_ml_s", [0.5, 1.0, 3.0, 6.0])
def test_a_tube_never_holds_more_than_it_can(flow_ml_s: float) -> None:
    graph, components = _bottle_through_three_tubes(flow_ml_s)
    worker = Worker(graph, components, SimConfig(dt=0.1))

    for _ in range(20):
        worker.step()
        for edge_id, queue in worker.transport_state.edge_queues.items():
            held = sum(pocket.volume for pocket in queue)
            # The solved flows of tubes in series agree only to about 1e-8.
            assert held <= edge_capacity(graph.edges[edge_id]) * (1 + 1e-4), edge_id


@pytest.mark.parametrize("flow_ml_s", [0.5, 3.0, 6.0])
def test_a_slug_arrives_with_no_gas_invented_ahead_of_it(flow_ml_s: float) -> None:
    """The gas reaching the receiver is exactly what the tubes started with.

    An overrun tube used to be padded with air each step, so liquid arrived later
    and behind a plug of gas that was never in the line.
    """
    graph, components = _bottle_through_three_tubes(flow_ml_s)
    worker = Worker(graph, components, SimConfig(dt=0.1))
    receiver = worker.inv_states["receiver.Inventory"]
    gas_at_start = receiver.gas_volume

    steps = round(4 * TUBE_M3 * 1e6 / flow_ml_s / 0.1) + 5
    for _ in range(steps):
        worker.step()

    # Two tubes' worth of initial gas went ahead of the liquid, and the receiver
    # pushes the same volume out through its own vent tube as it takes in.
    assert receiver.liq_volume > 0.0
    arrived = worker.inv_states["receiver.Inventory"].liq_volume
    pushed_through = flow_ml_s * 1e-6 * steps * 0.1
    assert arrived == pytest.approx(pushed_through - 2 * TUBE_M3, rel=0.02)
    assert receiver.liq_volume + receiver.gas_volume == pytest.approx(gas_at_start)


@pytest.mark.parametrize("flow_ml_s", [0.5, 3.0, 6.0])
def test_liquid_is_conserved_along_the_line(flow_ml_s: float) -> None:
    graph, components = _bottle_through_three_tubes(flow_ml_s)
    worker = Worker(graph, components, SimConfig(dt=0.1))
    start = worker.inv_states["bottle.Inventory"].liq_volume

    for _ in range(30):
        worker.step()

    in_tubes = sum(
        pocket.volume
        for queue in worker.transport_state.edge_queues.values()
        for pocket in queue
        if pocket.phase_kind == PhaseKind.LIQUID
    )
    total = (
        worker.inv_states["bottle.Inventory"].liq_volume
        + worker.inv_states["receiver.Inventory"].liq_volume
        + worker.inv_states["waste.Inventory"].liq_volume
        + in_tubes
    )
    assert total == pytest.approx(start, rel=1e-9)


def test_results_do_not_depend_on_the_time_step() -> None:
    def delivered(dt: float) -> float:
        graph, components = _bottle_through_three_tubes(flow_ml_s=3.0)
        worker = Worker(graph, components, SimConfig(dt=dt))
        for _ in range(round(1.0 / dt)):
            worker.step()
        return worker.inv_states["receiver.Inventory"].liq_volume

    assert delivered(0.1) == pytest.approx(delivered(0.05), rel=0.01)


@pytest.mark.parametrize("flow_ml_s", [0.5, 3.0])
def test_a_vessel_drains_to_empty(flow_ml_s: float) -> None:
    """An RV holding 50 uL, less than one step moves at 3 mL/s, still empties."""
    graph, components = _bottle_through_three_tubes(flow_ml_s, liquid_ml=0.05)
    worker = Worker(graph, components, SimConfig(dt=0.1))

    for _ in range(20):
        worker.step()

    assert worker.inv_states["bottle.Inventory"].liq_volume == pytest.approx(
        0.0, abs=1e-12
    )
    assert worker.inv_states["bottle.Inventory"].liq_species_moles[
        "water"
    ] == pytest.approx(0.0, abs=1e-9)
