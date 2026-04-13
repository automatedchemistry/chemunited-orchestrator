from chemunited.core.utils.internal_quantity import ChemQuantityValidator, ChemUnitQuantity
from chemunited.core.components import VesselComponentData, VesselMode
from chemunited.core.common.enums import GroupParameterCategory
from chemunited.qt.elements.component.graph_item import GraphComponent
from dataclasses import dataclass
from typing import ClassVar, Annotated
from pydantic import Field


@dataclass
class VialData(VesselComponentData):
    top_access: int = 1
    bottom_access: int = 0


class VialMode(VesselMode):

    top_access: int = Field(
        default=1,
        ge=1,
        title="Access at the top",
        description="Access connections at the top of the flask.",
        json_schema_extra={
            "group": GroupParameterCategory.PROPERTY.value,
            "editable": False,
            "lock_reason": "Internal Chosen",
            "visible": False
        },
    )
    bottom_access: int = Field(
        default=0,
        ge=1,
        title="Access at the bottom",
        description="Access connections at the bottom of the flask.",
        json_schema_extra={
            "group": GroupParameterCategory.PROPERTY.value,
            "editable": False,
            "lock_reason": "Internal Chosen",
            "visible": False
        },
    )


class Vial(GraphComponent[VialData]):
    METADATA: ClassVar[type[VialData]] = VialData
    BASEMODE: ClassVar[type[VialMode]] = VialMode
    SVG_SCALE: ClassVar[float] = 0.5

    def build(self) -> None:
        self._data.ports_by_number[1].relative_position = (0, -11)
        self._data.ports_by_number[2].relative_position = (0, 10)
        super().build()
