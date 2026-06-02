from typing import ClassVar

from chemunited_core.components import ComponentData, ComponentMode
from chemunited.qt.elements.component.graph_item import GraphComponent


class HPLCPump(GraphComponent[ComponentData]):
    METADATA: ClassVar[type[ComponentData]] = ComponentData
    BASEMODE: ClassVar[type[ComponentMode]] = ComponentMode

    def build(self, svg_path: str | None = None) -> None:
        self._data.ports_by_number[1].relative_position = (14, 33)
        self._data.ports_by_number[2].relative_position = (35, 33)
        return super().build(svg_path=":/components_icons/components/HPLCPump.svg")
