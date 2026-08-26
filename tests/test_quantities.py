from __future__ import annotations

from typing import Annotated

import pytest
from chemunited_quantities import ChemQuantityValidator, ChemUnitQuantity
from pydantic import BaseModel


@pytest.mark.parametrize(
    "value",
    [
        "0 degC",
        "0 \N{DEGREE SIGN}C",
        "0 degree_Celsius",
        "0 celsius",
    ],
)
def test_absolute_celsius_aliases(value: str) -> None:
    quantity = ChemUnitQuantity(value)

    assert quantity.to("degC").magnitude == pytest.approx(0)
    assert quantity.to("K").magnitude == pytest.approx(273.15)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("-12.5 degC", -12.5),
        (".5 \N{DEGREE SIGN}C", 0.5),
        ("1e2 degree_Celsius", 100),
    ],
)
def test_absolute_celsius_numeric_formats(value: str, expected: float) -> None:
    assert ChemUnitQuantity(value).to("degC").magnitude == pytest.approx(expected)


def test_delta_celsius_remains_temperature_difference() -> None:
    quantity = ChemUnitQuantity("10 delta_degC")

    assert quantity.units == ChemUnitQuantity(1, "delta_degC").units
    assert quantity.magnitude == pytest.approx(10)


def test_bare_c_remains_coulomb() -> None:
    quantity = ChemUnitQuantity("2 C")

    assert quantity.to("coulomb").magnitude == pytest.approx(2)


@pytest.mark.parametrize("value", ["5 ml", "5 ml/min"])
def test_non_offset_units_remain_supported(value: str) -> None:
    assert ChemUnitQuantity(value).magnitude == pytest.approx(5)


def test_construction_helpers_use_shared_parser() -> None:
    parsed = ChemUnitQuantity.parse("0 \N{DEGREE SIGN}C")
    converted = ChemUnitQuantity.from_any("0 degree_Celsius")

    assert parsed.to("K").magnitude == pytest.approx(273.15)
    assert converted.to("K").magnitude == pytest.approx(273.15)


class TemperatureModel(BaseModel):
    temperature: Annotated[
        ChemUnitQuantity,
        ChemQuantityValidator("degC"),
    ]


@pytest.mark.parametrize(
    "value",
    [
        "0 degC",
        "0 \N{DEGREE SIGN}C",
        "0 degree_Celsius",
        "0 celsius",
        {"magnitude": 0, "units": "\N{DEGREE SIGN}C"},
    ],
)
def test_pydantic_validation_accepts_celsius_aliases(value: object) -> None:
    model = TemperatureModel(temperature=value)

    assert model.temperature.to("K").magnitude == pytest.approx(273.15)
