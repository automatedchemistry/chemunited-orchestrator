from chemunited.core.components import ComponentData, ComponentMode
from chemunited.qt.elements.component.graph_item import GraphComponent
from typing import ClassVar


class FlowMeter(GraphComponent[ComponentData]):
    METADATA: ClassVar[type[ComponentData]] = ComponentData
    BASEMODE: ClassVar[type[ComponentMode]] = ComponentMode

    def build(self, svg_path: str | None = None) -> None:
        self._data.ports_by_number[1].relative_position = (42, 22)
        self._data.ports_by_number[2].relative_position = (-42, 22)
        return super().build(svg_path=f":/components_icons/components/FlowMeter.svg")

    
