from typing import ClassVar

from chemunited_core.figure_registry.pipes import SeparatorData, SeparatorMode
from chemunited.qt.elements.component.graph_item import GraphComponent


class Separator(GraphComponent[SeparatorData]):
    METADATA: ClassVar[type[SeparatorData]] = SeparatorData
    BASEMODE: ClassVar[type[SeparatorMode]] = SeparatorMode

    def build(self, svg_path: str | None = None) -> None:
        self._data.ports_by_number[1].relative_position = (-40, -26)
        self._data.ports_by_number[2].relative_position = (-40, 3)
        return super().build(svg_path=":/components_icons/components/Separator.svg")
