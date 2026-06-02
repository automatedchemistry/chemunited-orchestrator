from typing import ClassVar

from chemunited_core.components import ComponentMode, NeutralComponentData
from chemunited.qt.elements.component.graph_item import GraphComponent


class PowerControl(GraphComponent[NeutralComponentData]):
    METADATA: ClassVar[type[NeutralComponentData]] = NeutralComponentData
    BASEMODE: ClassVar[type[ComponentMode]] = ComponentMode
    SVG_SCALE: ClassVar[float] = 0.8

    def build(self, svg_path: str | None = None) -> None:
        super().build(svg_path=":/components_icons/components/Power.svg")


class PowerSwitch(GraphComponent[NeutralComponentData]):
    METADATA: ClassVar[type[NeutralComponentData]] = NeutralComponentData
    BASEMODE: ClassVar[type[ComponentMode]] = ComponentMode
    SVG_SCALE: ClassVar[float] = 0.8

    def build(self, svg_path: str | None = None) -> None:
        super().build(svg_path=":/components_icons/components/Power.svg")


class PhidgetBubbleSensorPowerComponent(GraphComponent[NeutralComponentData]):
    METADATA: ClassVar[type[NeutralComponentData]] = NeutralComponentData
    BASEMODE: ClassVar[type[ComponentMode]] = ComponentMode
    SVG_SCALE: ClassVar[float] = 0.8

    def build(self, svg_path: str | None = None) -> None:
        super().build(svg_path=":/components_icons/components/Power.svg")
