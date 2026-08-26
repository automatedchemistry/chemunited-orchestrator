from dataclasses import dataclass
from typing import Annotated

from chemunited_quantities import (
    ChemQuantityValidator,
    ChemUnitQuantity,
)
from pint.errors import DimensionalityError
from pydantic import Field
from typing_extensions import override

from chemunited_core.common.enums import ConnectionType, GroupParameterCategory
from chemunited_core.components import ComponentMode, NeutralComponentData
from chemunited_core.components.command import PutResult
from chemunited_core.components.internals import Port


def _temperature_quantity(value: object) -> ChemUnitQuantity:
    if isinstance(value, str):
        stripped = value.strip()
        parts = stripped.split()
        if len(parts) == 2 and parts[1] in {"C", "c", "degC", "degc", "celsius"}:
            return ChemUnitQuantity(float(parts[0]) + 273.15, "K")
        return ChemUnitQuantity(stripped).to("K")
    quantity = ChemUnitQuantity.from_any(value)
    try:
        return quantity.to("K")
    except DimensionalityError:
        if str(quantity.units) == "coulomb":
            return ChemUnitQuantity(float(quantity.magnitude) + 273.15, "K")
        raise


class TemperatureControlMode(ComponentMode):
    temperature: Annotated[ChemUnitQuantity, ChemQuantityValidator("K")] = Field(
        default=ChemUnitQuantity("298.15 K"),
        title="Temperature",
        description="Temperature control setpoint.",
        json_schema_extra={
            "group": GroupParameterCategory.STATUS.value,
        },
    )


@dataclass
class TemperatureControlData(NeutralComponentData):
    temperature: ChemUnitQuantity = ChemUnitQuantity("298.15 K")

    @property
    def temperature_value(self) -> float:
        return float(self.temperature.to_base_units().magnitude)

    @override
    def apply(self, command: str, **kwargs) -> PutResult:
        if command not in {"temperature", "set_temperature"}:
            return PutResult()

        if "temp" not in kwargs:
            return PutResult()

        self.temperature = _temperature_quantity(kwargs["temp"])
        return PutResult()

    @override
    def get(self, command: str, **kwargs) -> float | None:
        if command in {"temperature", "temperature-setpoint"}:
            return self.temperature_value
        return None

    @override
    def internal_structure(self) -> None:
        self.port_pairs = [(1,)]
        self.ports_by_number = {
            1: Port(
                number=1,
                component=self.name,
                category=ConnectionType.HEAT,
                relative_position=(25, 0),
            ),
        }
        self.internal_edges = {}
        self.internal_inventories = {}


class PeltierCoolerTemperatureControlMode(TemperatureControlMode): ...


@dataclass
class PeltierCoolerTemperatureControlData(TemperatureControlData):
    @override
    def internal_structure(self) -> None:
        self.port_pairs = [(1,)]
        self.ports_by_number = {
            1: Port(
                number=1,
                component=self.name,
                category=ConnectionType.HEAT,
                relative_position=(50, 0),
            )
        }
        self.internal_edges = {}
        self.internal_inventories = {}


class HeiConnectTemperatureControlMode(TemperatureControlMode): ...


@dataclass
class HeiConnectTemperatureControlData(TemperatureControlData): ...
