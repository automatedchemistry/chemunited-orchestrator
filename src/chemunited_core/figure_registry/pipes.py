from dataclasses import dataclass
from typing import Annotated, ClassVar

from chemunited_quantities import (
    ChemQuantityValidator,
    ChemUnitQuantity,
)
from pydantic import Field

from chemunited_core.common.enums import GroupParameterCategory
from chemunited_core.components import (
    ComponentData,
    ComponentMode,
    PressureControlData,
    VesselComponentData,
    VesselMode,
)
from chemunited_core.components.enums import ComponentType


class SourceMode(ComponentMode):

    setpoint: Annotated[ChemUnitQuantity, ChemQuantityValidator("bar")] = Field(
        default=ChemUnitQuantity("1 bar"),
        title="Pressure",
        description=(
            "Pressure at the outlet port. Note: 1 bar is approximately \n"
            "atmospheric pressure at sea level."
        ),
        json_schema_extra={
            "group": GroupParameterCategory.STATUS.value,
        },
    )


@dataclass
class SourceData(PressureControlData):
    COMPONENT_TYPE: ClassVar[ComponentType] = ComponentType.UTENSIL


class SinkMode(VesselMode):
    capacity: Annotated[ChemUnitQuantity, ChemQuantityValidator("ml")] = Field(
        default=ChemUnitQuantity("1e10 l"),
        json_schema_extra={
            "visible": False,
        },
    )
    top_access: int = Field(
        default=1,
        json_schema_extra={
            "visible": False,
        },
    )
    bottom_access: int = Field(
        default=0,
        json_schema_extra={
            "visible": False,
        },
    )
    heat_exchange: bool = Field(
        default=False,
        json_schema_extra={
            "visible": False,
        },
    )
    pressure_access: bool = Field(
        default=False,
        json_schema_extra={
            "visible": False,
        },
    )


@dataclass
class SinkData(VesselComponentData):
    capacity: ChemUnitQuantity = ChemUnitQuantity("1e10 l")
    top_access: int = 1
    bottom_access: int = 0
    heat_exchange: bool = False


class SeparatorMode(ComponentMode): ...


@dataclass
class SeparatorData(ComponentData):
    COMPONENT_TYPE: ClassVar[ComponentType] = ComponentType.UTENSIL
