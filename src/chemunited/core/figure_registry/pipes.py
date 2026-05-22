from dataclasses import dataclass
from typing import Annotated, ClassVar

from pydantic import Field

from chemunited.core.components import (
    ComponentData,
    ComponentMode,
    PressureControlData,
    PressureControlMode,
    VesselComponentData,
    VesselMode,
)
from chemunited.core.components.enums import ComponentType
from chemunited.core.utils.internal_quantity import (
    ChemQuantityValidator,
    ChemUnitQuantity,
)


class SourceMode(PressureControlMode): ...


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
