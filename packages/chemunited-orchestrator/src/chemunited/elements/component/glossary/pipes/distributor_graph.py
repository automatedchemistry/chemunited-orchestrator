from typing import ClassVar

from chemunited_core.components import JunctionData
from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtGui import QPen

from chemunited.elements.component.component_parts import SceneItem
from chemunited.elements.component.graph_item import GraphComponent


class Body(SceneItem):

    def __init__(self, data: JunctionData, parent=None):

        radius = int(40 * max(7, data.number_ports) / 10)

        super().__init__(width=2 * radius, height=2 * radius, parent=parent)

        self._data = data

    def paint(self, painter, option, widget=None):

        painter.setPen(QPen(self.theme_colors[self.current_theme]["gradient"], 3))
        painter.setBrush(Qt.transparent)  # type: ignore[attr-defined]

        x1, y1 = 0, 0

        for port in self._data.ports_by_number.values():

            x2, y2 = port.relative_position

            p1 = QPointF(x1, y1)
            p2 = QPointF(x2, y2)

            # Convert to standard float before passing to drawLine
            painter.drawLine(p1, p2)


class Distributor(GraphComponent[JunctionData]):
    FIGURE: ClassVar[str] = "Distributor"

    def build(self) -> None:
        super().build()
        self.addToGroup(Body(self._data, parent=self))
