from chemunited.core.components import VesselComponentData, VesselMode
from chemunited.qt.elements.component.graph_item import GraphComponent
from chemunited.core.utils.internal_quantity import (
    ChemUnitQuantity,
)
from pydantic import Field
from typing import ClassVar


class SinkMode(VesselMode):
    capacity: float = Field(
        default=ChemUnitQuantity("1e10 l"), # No limit
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


class Sink(GraphComponent[VesselComponentData]):
    METADATA: ClassVar[type[VesselComponentData]] = VesselComponentData
    BASEMODE: ClassVar[type[SinkMode]] = SinkMode

    def build(self, svg_path: str | None = None) -> None:
        self._data.ports_by_number[1].relative_position = (-40, 0)
        super().build(svg_path=f":/components_icons/components/SourceSink.svg")

