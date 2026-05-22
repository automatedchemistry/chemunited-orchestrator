from typing import ClassVar

from chemunited.core.figure_registry.thermal import (
    TemperatureControlData,
    TemperatureControlMode,
)
from chemunited.qt.elements.component.graph_item import GraphComponent


class TemperatureControl(GraphComponent[TemperatureControlData]):
    METADATA: ClassVar[type[TemperatureControlData]] = TemperatureControlData
    BASEMODE: ClassVar[type[TemperatureControlMode]] = TemperatureControlMode

    def build(self, svg_path: str | None = None) -> None:
        return super().build(svg_path=":/components_icons/components/Chiller.svg")
