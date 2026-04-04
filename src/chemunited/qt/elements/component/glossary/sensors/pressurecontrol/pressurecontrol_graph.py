from typing import ClassVar

from chemunited.core.components import PressureControlData, PressureControlMode
from chemunited.qt.draw.elements.component.graph_item import GraphComponent


class PressureControl(GraphComponent[PressureControlData]):
    METADATA: ClassVar[type[PressureControlData]] = PressureControlData
    BASEMODE: ClassVar[type[PressureControlMode]] = PressureControlMode
