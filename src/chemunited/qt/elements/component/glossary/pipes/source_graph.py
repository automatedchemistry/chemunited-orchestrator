from typing import ClassVar

from chemunited.core.components import PressureControlData, PressureControlMode
from chemunited.qt.elements.component.graph_item import GraphComponent


class Source(GraphComponent[PressureControlData]):
    METADATA: ClassVar[type[PressureControlData]] = PressureControlData
    BASEMODE: ClassVar[type[PressureControlMode]] = PressureControlMode

    def build(self, svg_path: str | None = None) -> None:
        self._data.ports_by_number[1].relative_position = (40, 0)
        super().build(svg_path=f":/components_icons/components/SourceSink.svg")
        self._svg.setRotation(180)

