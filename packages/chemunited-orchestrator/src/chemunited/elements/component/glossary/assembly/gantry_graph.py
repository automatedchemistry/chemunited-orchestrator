import re
from typing import ClassVar

from PyQt5.QtGui import QFont

from chemunited.elements.component.component_parts import TextElement
from chemunited.elements.component.graph_item import GraphComponent
from chemunited_core.common.constant import PATTERN_DIMENSION
from chemunited_core.figure_registry import Gantry1DData


class GantryGraph(GraphComponent[Gantry1DData]):
    LABEL_MARGIN: ClassVar[int] = 8

    def build(self) -> None:
        super().build()
        self._characteristic_label = TextElement(
            self._gantry_characteristic(),
            font=self._label_font(),
            parent=self,
        )
        self._characteristic_label.setZValue(2)

        svg_rect = self._svg.mapRectToParent(self._svg.boundingRect())
        self._characteristic_label.setPos(
            svg_rect.left() + self.LABEL_MARGIN,
            svg_rect.top() + self.LABEL_MARGIN - 5,
        )
        self.addToGroup(self._characteristic_label)

    def _gantry_characteristic(self) -> str:
        for candidate in (self._data.figure, type(self).FIGURE, type(self).__name__):
            if match := re.search(r"([13]D)\b", candidate):
                return match.group(1)
        return ""

    @staticmethod
    def _label_font() -> QFont:
        font = QFont()
        font.setBold(True)
        font.setPixelSize(PATTERN_DIMENSION // 3)
        return font


class Gantry1D(GantryGraph):
    FIGURE: ClassVar[str] = "Gantry1D"


class Gantry3D(GantryGraph):
    FIGURE: ClassVar[str] = "Gantry3D"
