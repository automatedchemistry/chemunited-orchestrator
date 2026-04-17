from dataclasses import dataclass
from typing import ClassVar

from pydantic import Field

from chemunited.core.common.enums import GroupParameterCategory
from chemunited.core.components import VesselComponentData, VesselMode
from chemunited.qt.elements.component.graph_item import GraphComponent


@dataclass
class VialData(VesselComponentData):
    top_access: int = 1
    bottom_access: int = 0


class VialMode(VesselMode):

    column: int = Field(
        default=1,
        ge=1,
        le=20,
        json_schema_extra={
            "group": GroupParameterCategory.PROPERTY.value,
            "editable": False,
            "lock_reason": "Internal Chosen",
            "visible": True,
        },
    )

    row: int = Field(
        default=1,
        ge=1,
        le=20,
        json_schema_extra={
            "group": GroupParameterCategory.PROPERTY.value,
            "editable": False,
            "lock_reason": "Internal Chosen",
            "visible": True,
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


class Vial(GraphComponent[VialData]):
    METADATA: ClassVar[type[VialData]] = VialData
    BASEMODE: ClassVar[type[VialMode]] = VialMode
    SVG_SCALE: ClassVar[float] = 0.5

    def build(self, svg_path: str | None = None) -> None:
        self._data.ports_by_number[1].relative_position = (0, -11)
        self._data.ports_by_number[2].relative_position = (0, 10)
        super().build()
