from typing import ClassVar

from chemunited.core.components import PressureControlData, PressureControlMode
from chemunited.qt.elements.component.graph_item import GraphComponent


class PressureControl(GraphComponent[PressureControlData]):
    METADATA: ClassVar[type[PressureControlData]] = PressureControlData
    BASEMODE: ClassVar[type[PressureControlMode]] = PressureControlMode

    def build(self, svg_path: str | None = None) -> None:
        self._data.ports_by_number[1].relative_position = (40, 27)
        return super().build(
            svg_path=":/components_icons/components/PressureControl.svg"
        )
