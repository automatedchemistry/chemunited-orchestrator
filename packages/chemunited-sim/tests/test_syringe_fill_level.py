"""The worker tells a syringe what's in its barrel, so full strokes can stop in time."""

from __future__ import annotations

import pytest

from chemunited_core.common.enums import ConnectionType
from chemunited_core.connections import EdgeData, EdgeMode
from chemunited_core.figure_registry import COMPONENTS
from chemunited_quantities import ChemUnitQuantity
from chemunited_sim.adapter import compile_graph, resync_component
from chemunited_sim.worker import SimConfig, Worker


def _make(figure: str, name: str, **kwargs):
    definition = COMPONENTS[figure]
    return definition.data_class.from_mode(definition.mode_class(name=name, **kwargs))


def _syringe_to_sink():
    pump = _make(
        "SyringePump",
        "pump",
        syringe_volume=ChemUnitQuantity("5 ml"),
        syringe_actual_volume=ChemUnitQuantity("1 ml"),
    )
    pump.internal_inventory.liq_content.volume = 1.0e-6
    pump.internal_inventory.liq_content.initial_species = {"water": 0.05}
    sink = _make("PressureControl", "sink")
    tube = EdgeData.from_mode(
        EdgeMode(
            name="pump_1_sink_1",
            origin="pump",
            origin_port=1,
            destination="sink",
            destination_port=1,
            classification=ConnectionType.HYDRAULIC,
            length="100 mm",
            diameter="1 mm",
        )
    )
    return pump, sink, tube


def test_worker_keeps_the_syringe_fill_level_current() -> None:
    pump, sink, tube = _syringe_to_sink()
    graph = compile_graph([pump, sink], [tube])
    worker = Worker(graph, [pump, sink], SimConfig(dt=0.1))

    assert pump.fill_m3 == pytest.approx(1.0e-6)

    pump.apply("infuse", rate="60 ml/min")
    resync_component(graph, pump)
    for _ in range(4):
        worker.step()

    assert pump.fill_m3 == pytest.approx(
        worker.inv_states["pump.Inventory"].liq_volume
        + worker.inv_states["pump.Inventory"].gas_volume
    )
    assert pump.fill_m3 < 1.0e-6


def test_infuse_all_empties_the_syringe_when_run_for_its_scheduled_time() -> None:
    pump, sink, tube = _syringe_to_sink()
    graph = compile_graph([pump, sink], [tube])
    worker = Worker(graph, [pump, sink], SimConfig(dt=0.1))
    pump.apply("infuse", rate="60 ml/min")
    pump.apply("stop")
    resync_component(graph, pump)

    result = pump.apply("infuse-all")
    resync_component(graph, pump)

    assert [s.command for s in result.scheduled] == ["stop"]
    assert result.scheduled[0].dt == pytest.approx(1.0)
    for _ in range(round(result.scheduled[0].dt / 0.1)):
        worker.step()

    assert worker.inv_states["pump.Inventory"].liq_volume == pytest.approx(
        0.0, abs=1e-9
    )
    assert pump.fill_m3 == pytest.approx(0.0, abs=1e-9)
