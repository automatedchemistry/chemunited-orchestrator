"""Tubes keep short queues: pockets of the same fluid become one as they arrive."""

from __future__ import annotations

from collections import deque

import pytest

from chemunited_core.common.enums import ConnectionType, PhaseKind
from chemunited_core.connections import EdgeData, EdgeMode
from chemunited_core.figure_registry import COMPONENTS
from chemunited_quantities import ChemUnitQuantity
from chemunited_sim.adapter import compile_graph
from chemunited_sim.hydraulics.models import HydraulicState
from chemunited_sim.transport.engine import _push_inflow, inject
from chemunited_sim.transport.junction import can_merge_neighbours
from chemunited_sim.transport.models import Pocket, TransportState
from chemunited_sim.worker import SimConfig, Worker

BIG = 1.0e-9


def _liquid(volume: float = BIG, moles: float = 1.0e-6, **kwargs) -> Pocket:
    species = kwargs.pop("species", {"solvent": moles})
    return Pocket(
        phase_kind=kwargs.pop("phase", PhaseKind.LIQUID),
        volume=volume,
        species_moles=species,
        temperature=kwargs.pop("temperature", 298.15),
        pressure=kwargs.pop("pressure", 101_325.0),
    )


def test_same_fluid_can_merge() -> None:
    assert can_merge_neighbours(_liquid(), _liquid(volume=2 * BIG, moles=2.0e-6))


def test_concentration_within_tolerance_can_merge() -> None:
    assert can_merge_neighbours(_liquid(), _liquid(moles=1.0005e-6))


def test_different_concentration_stays_apart() -> None:
    assert not can_merge_neighbours(_liquid(), _liquid(moles=1.01e-6))


def test_different_species_stay_apart() -> None:
    assert not can_merge_neighbours(_liquid(), _liquid(species={"reagent": 1.0e-6}))


def test_a_species_only_one_pocket_holds_keeps_them_apart() -> None:
    mixed = _liquid(species={"solvent": 1.0e-6, "reagent": 1.0e-9})
    assert not can_merge_neighbours(_liquid(), mixed)


def test_different_phases_stay_apart_even_when_tiny() -> None:
    gas = _liquid(volume=1.0e-12, phase=PhaseKind.GAS)
    assert not can_merge_neighbours(_liquid(volume=1.0e-12), gas)


def test_different_temperature_stays_apart() -> None:
    assert not can_merge_neighbours(_liquid(), _liquid(temperature=300.0))


def test_tiny_pocket_merges_whatever_it_holds() -> None:
    tiny = _liquid(volume=1.0e-12, species={"reagent": 1.0e-9}, temperature=350.0)
    assert can_merge_neighbours(_liquid(), tiny)
    assert can_merge_neighbours(tiny, _liquid())


def test_empty_pockets_of_carrier_fluid_can_merge() -> None:
    assert can_merge_neighbours(_liquid(species={}), _liquid(species={}))


def test_push_merges_at_the_inflow_end_and_conserves_everything() -> None:
    far = _liquid(species={"other": 1.0e-6})
    near = _liquid(moles=2.0e-6, volume=2 * BIG, temperature=298.16, pressure=2.0e5)
    queue = deque([far, near])

    _push_inflow(queue, _liquid(temperature=298.22, pressure=1.0e5), 1.0e-9)

    assert len(queue) == 2
    assert queue[0] is far
    merged = queue[1]
    assert merged.volume == pytest.approx(3 * BIG)
    assert merged.species_moles == {"solvent": pytest.approx(3.0e-6)}
    assert merged.temperature == pytest.approx(298.18)
    assert merged.pressure == pytest.approx((2 * 2.0e5 + 1.0e5) / 3)


def test_push_uses_the_other_end_when_flow_reverses() -> None:
    near = _liquid(moles=2.0e-6, volume=2 * BIG)
    far = _liquid(species={"other": 1.0e-6})
    queue = deque([near, far])

    _push_inflow(queue, _liquid(), -1.0e-9)

    assert len(queue) == 2
    assert queue[1] is far
    assert queue[0].volume == pytest.approx(3 * BIG)


@pytest.mark.parametrize("flow", [1.0e-9, -1.0e-9])
def test_push_keeps_a_different_fluid_at_the_inflow_end(flow: float) -> None:
    old = _liquid()
    new = _liquid(species={"reagent": 1.0e-6})
    queue = deque([old])

    _push_inflow(queue, new, flow)

    assert list(queue) == ([old, new] if flow > 0 else [new, old])


def test_inject_merges_what_it_adds() -> None:
    state = TransportState(edge_queues={"edge": deque([_liquid()])})
    hyd_state = HydraulicState(pressures={}, flows={"edge": 1.0e-9})

    result = inject(state, {"edge": [_liquid()]}, hyd_state)

    assert len(result.edge_queues["edge"]) == 1
    assert result.edge_queues["edge"][0].volume == pytest.approx(2 * BIG)


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


def test_idle_lines_stay_short_over_a_long_run() -> None:
    """Pressurised gas held behind closed valves. A closed valve leaks a little, so
    every line moves a tiny, ever-changing mixture each step. Without merging, each
    step adds pockets that nothing removes, and steps slow down in proportion."""
    argon = _make("Source", "argon", setpoint=ChemUnitQuantity("1.2 bar"))
    hub = _make("Distributor", "hub", number_ports=4)
    valves = [_make("SolenoidValve", f"v{i}") for i in range(3)]
    waste = _make("Sink", "waste")
    edges = [_tube("argon", 1, "hub", 1)]
    for index, valve in enumerate(valves):
        edges.append(_tube("hub", index + 2, valve.name, 1))
        edges.append(_tube(valve.name, 2, "waste", 1))
    components = [argon, hub, *valves, waste]
    graph = compile_graph(components, edges)
    worker = Worker(graph, components, SimConfig(dt=0.1))
    volume_at_start = None

    for step in range(2_000):
        worker.step()
        if step == 0:
            volume_at_start = _total_volume(worker)

    assert _pocket_count(worker) < 10 * len(edges)
    assert _total_volume(worker) == pytest.approx(volume_at_start, rel=1e-4)


def _pocket_count(worker: Worker) -> int:
    return sum(len(queue) for queue in worker.transport_state.edge_queues.values())


def _total_volume(worker: Worker) -> float:
    return sum(
        pocket.volume
        for queue in worker.transport_state.edge_queues.values()
        for pocket in queue
    )
