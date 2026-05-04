from typing import ClassVar

from chemunited.core.components import ComponentData, ComponentMode
from chemunited.core.components.enums import ComponentType
from chemunited.qt.elements.component.graph_item import GraphComponent


class Separator(GraphComponent[ComponentData]):
    COMPONENT_TYPE: ClassVar[ComponentType] = ComponentType.UTENSIL
    METADATA: ClassVar[type[ComponentData]] = ComponentData
    BASEMODE: ClassVar[type[ComponentMode]] = ComponentMode

    def build(self, svg_path: str | None = None) -> None:
        self._data.ports_by_number[1].relative_position = (-40, -26)
        self._data.ports_by_number[2].relative_position = (-40, 3)
        return super().build(svg_path=":/components_icons/components/Separator.svg")
