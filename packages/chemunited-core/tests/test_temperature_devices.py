"""Simulated temperature devices answer what protocols send to the real ones."""

import pytest

from chemunited_core.figure_registry import COMPONENTS
from chemunited_core.figure_registry.thermal import (
    PeltierCoolerTemperatureControlData,
    PeltierCoolerTemperatureControlMode,
    TemperatureSensorData,
    TemperatureSensorMode,
)


def _peltier() -> PeltierCoolerTemperatureControlData:
    return PeltierCoolerTemperatureControlData.from_mode(
        PeltierCoolerTemperatureControlMode(name="peltier")
    )


@pytest.mark.parametrize("keyword", ["temp", "temperature"])
def test_setpoint_is_read_from_either_spelling(keyword: str) -> None:
    peltier = _peltier()

    peltier.apply("temperature", **{keyword: "-20 degC"})

    assert peltier.temperature_value == pytest.approx(253.15)


def test_setpoint_is_left_alone_without_a_value() -> None:
    peltier = _peltier()

    peltier.apply("temperature")

    assert peltier.temperature_value == pytest.approx(298.15)


def test_set_temperature_command_spellings_all_apply() -> None:
    for command in ("temperature", "set_temperature", "set-temperature"):
        peltier = _peltier()
        peltier.apply(command, temp="10 degC")
        assert peltier.temperature_value == pytest.approx(283.15)


def test_temperature_control_reports_degrees_celsius() -> None:
    peltier = _peltier()
    peltier.apply("temperature", temperature="-20 degC")

    assert peltier.get("temperature") == pytest.approx(-20.0)
    assert peltier.get("temperature-setpoint") == pytest.approx(-20.0)
    assert peltier.get("something-else") is None


def test_temperature_sensor_is_registered_with_its_own_data_class() -> None:
    assert COMPONENTS["TemperatureSensor"].data_class is TemperatureSensorData
    assert COMPONENTS["TemperatureSensor"].mode_class is TemperatureSensorMode
    assert COMPONENTS["TemperatureSensor"].figure_base == "PT100"


def test_temperature_sensor_reports_its_reading_in_degrees_celsius() -> None:
    sensor = TemperatureSensorData.from_mode(
        TemperatureSensorMode(name="tc", measures="reactor")
    )

    assert sensor.measures == "reactor"
    assert sensor.get("temperature") == pytest.approx(25.0)

    sensor.reading_k = 253.15

    assert sensor.get("temperature") == pytest.approx(-20.0)
    assert sensor.get("something-else") is None
