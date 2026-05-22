from typing import ClassVar

from chemunited.core.figure_registry.thermal import (
    PeltierCoolerTemperatureControlData,
    PeltierCoolerTemperatureControlMode,
)
from chemunited.qt.elements.component.graph_item import GraphComponent


class PeltierCoolerTemperatureControl(
    GraphComponent[PeltierCoolerTemperatureControlData]
):
    METADATA: ClassVar[type[PeltierCoolerTemperatureControlData]] = (
        PeltierCoolerTemperatureControlData
    )
    BASEMODE: ClassVar[type[PeltierCoolerTemperatureControlMode]] = (
        PeltierCoolerTemperatureControlMode
    )
    SVG_SCALE: ClassVar[float] = 2

    def build(self, svg_path: str | None = None) -> None:
        super().build(svg_path=":/components_icons/components/Peltier.svg")
