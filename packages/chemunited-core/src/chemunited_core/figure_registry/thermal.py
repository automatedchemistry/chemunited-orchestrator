from dataclasses import dataclass, field
from typing import Annotated

from pint.errors import DimensionalityError
from pydantic import Field
from typing_extensions import override

from chemunited_core.common.constant import AMBIENT_TEMPERATURE_K
from chemunited_core.common.enums import ConnectionType, GroupParameterCategory
from chemunited_core.components import ComponentMode, NeutralComponentData
from chemunited_core.components.command import PutResult
from chemunited_core.components.internals import Port
from chemunited_quantities import (
    ChemQuantityValidator,
    ChemUnitQuantity,
)

_KELVIN_AT_0_DEGC = 273.15


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
        if command not in {"temperature", "set_temperature", "set-temperature"}:
            return PutResult()

        # flowchem's temperature controls take `temp`, its Peltier `temperature`.
        setpoint = kwargs.get("temp", kwargs.get("temperature"))
        if setpoint is None:
            return PutResult()

        self.temperature = _temperature_quantity(setpoint)
        return PutResult()

    @override
    def get(self, command: str, **kwargs) -> float | None:
        """The setpoint in degC, which is what the real devices report."""
        if command in {"temperature", "temperature-setpoint"}:
            return self.temperature_value - _KELVIN_AT_0_DEGC
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


class TemperatureSensorMode(ComponentMode):
    measures: str = Field(
        default="",
        title="Measured Vessel",
        description=(
            "Name of the vessel this sensor reads in a simulation. Leave empty "
            "to read the only vessel with a heat link."
        ),
        json_schema_extra={
            "group": GroupParameterCategory.PROPERTY.value,
        },
    )


@dataclass
class TemperatureSensorData(NeutralComponentData):
    """A thermocouple or PT100. A simulation keeps ``reading_k`` current."""

    measures: str = ""
    reading_k: float = field(
        default=AMBIENT_TEMPERATURE_K, init=False, repr=False, compare=False
    )

    @override
    def get(self, command: str, **kwargs) -> float | None:
        """The reading in degC, which is what the real devices report."""
        if command == "temperature":
            return self.reading_k - _KELVIN_AT_0_DEGC
        return None
