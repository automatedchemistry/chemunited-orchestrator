"""A simulated temperature sensor reads the vessel it measures."""

from __future__ import annotations

import pytest
from loguru import logger

from chemunited_core.common.enums import ConnectionType
from chemunited_core.connections import EdgeData, EdgeMode
from chemunited_core.figure_registry import COMPONENTS
from chemunited_quantities import ChemUnitQuantity
from chemunited_sim.adapter import compile_graph
from chemunited_sim.worker import SimConfig, Worker


def _make(figure: str, name: str, **kwargs):
    definition = COMPONENTS[figure]
    return definition.data_class.from_mode(definition.mode_class(name=name, **kwargs))


def _heat_link(controller: str, vessel: str) -> EdgeData:
    return EdgeData.from_mode(
        EdgeMode(
            name=f"{controller}_{vessel}_heat",
            origin=controller,
            origin_port=1,
            destination=vessel,
            destination_port=2,
            classification=ConnectionType.HEAT,
        )
    )


def _heated_vessel(name: str):
    vessel = _make(
        "GlassBottle",
        name,
        heat_exchange=True,
        heat_transfer_coefficient=ChemUnitQuantity("100 W/(m^2*K)"),
    )
    vessel.internal_inventory.gas_content.initial_species = {"air": 1.0e-5}
    return vessel


@pytest.fixture
def warnings():
    messages: list[str] = []
    sink = logger.add(lambda m: messages.append(m.record["message"]), level="WARNING")
    yield messages
    logger.remove(sink)


def test_sensor_reads_the_only_heat_linked_vessel() -> None:
    controller = _make("PeltierCoolerTemperatureControl", "chiller")
    vessel = _heated_vessel("reactor")
    sensor = _make("TemperatureSensor", "tc")
    components = [controller, vessel, sensor]
    graph = compile_graph(components, [_heat_link("chiller", "reactor")])
    worker = Worker(graph, components, SimConfig(dt=0.1))

    assert sensor.get("temperature") == pytest.approx(25.0)

    controller.apply("temperature", temperature="-20 degC")
    for _ in range(50):
        worker.step()

    reading = sensor.get("temperature")
    actual = worker.inv_states["reactor.Inventory"].temperature - 273.15
    assert reading == pytest.approx(actual)
    assert reading < 25.0


def test_sensor_prefers_the_vessel_it_names(warnings) -> None:
    controller = _make("PeltierCoolerTemperatureControl", "chiller")
    heated = _heated_vessel("reactor")
    other = _make("GlassBottle", "other")
    other.internal_inventory.gas_content.initial_species = {"air": 1.0e-5}
    other.internal_inventory.gas_content.initial_temperature = 310.0
    sensor = _make("TemperatureSensor", "tc", measures="other")
    components = [controller, heated, other, sensor]
    graph = compile_graph(components, [_heat_link("chiller", "reactor")])

    worker = Worker(graph, components, SimConfig(dt=0.1))

    expected = worker.inv_states["other.Inventory"].temperature - 273.15
    assert sensor.get("temperature") == pytest.approx(expected)
    assert not [m for m in warnings if "temperature sensor" in m]


def test_sensor_with_several_candidates_reports_ambient_and_warns_once(
    warnings,
) -> None:
    controller_a = _make("PeltierCoolerTemperatureControl", "chillera")
    controller_b = _make("PeltierCoolerTemperatureControl", "chillerb")
    vessel_a = _heated_vessel("reactora")
    vessel_b = _heated_vessel("reactorb")
    sensor = _make("TemperatureSensor", "tc")
    components = [controller_a, controller_b, vessel_a, vessel_b, sensor]
    graph = compile_graph(
        components,
        [_heat_link("chillera", "reactora"), _heat_link("chillerb", "reactorb")],
    )

    worker = Worker(graph, components, SimConfig(dt=0.1))
    for _ in range(5):
        worker.step()

    assert sensor.get("temperature") == pytest.approx(25.0)
    assert len([m for m in warnings if "temperature sensor 'tc'" in m]) == 1


def test_sensor_naming_something_without_an_inventory_warns(warnings) -> None:
    sensor = _make("TemperatureSensor", "tc", measures="nothing")
    graph = compile_graph([sensor], [])

    Worker(graph, [sensor], SimConfig(dt=0.1))

    assert sensor.get("temperature") == pytest.approx(25.0)
    assert [m for m in warnings if "temperature sensor 'tc'" in m]
