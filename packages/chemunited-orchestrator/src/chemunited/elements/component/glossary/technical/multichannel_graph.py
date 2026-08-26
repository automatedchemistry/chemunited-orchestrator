from typing import ClassVar

from chemunited_core.figure_registry.technical import MultiChannelData
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QBrush, QColor, QPen

from chemunited.elements.component.component_parts import SceneItem
from chemunited.elements.component.graph_item import GraphComponent


class MultiChannelBory(SceneItem):
    def __init__(self, data: "MultiChannelData") -> None:
        self._data = data
        super().__init__(width=15, height=16 * data.channels + 4)

    def paint(self, painter, option, widget=None) -> None:
        painter.setPen(QPen(Qt.GlobalColor.black, 1))
        painter.setBrush(QBrush(Qt.GlobalColor.white))
        painter.drawRect(self.boundingRect())
        value = self._data.active
        r = 4
        for i in range(self._data.channels):
            if value:
                color = QColor("#8BC34A") if value[i] else QColor("#E8F5E9")
                painter.setPen(QPen(color, 2))
            painter.drawEllipse(-r, int(-self.height / 2 + i * 16 + 4), 2 * r, 2 * r)


class MultiChannelADC(GraphComponent[MultiChannelData]):
    FIGURE: ClassVar[str] = "MultiChannelADC"

    def build(self) -> None:
        self.bory = MultiChannelBory(self._data)
        self.addToGroup(self.bory)
        super().build()
        self._svg.setPos(-20, self.bory.height / 2)


class MultiChannelDAC(GraphComponent[MultiChannelData]):
    FIGURE: ClassVar[str] = "MultiChannelDAC"

    def build(self) -> None:
        self.bory = MultiChannelBory(self._data)
        self.addToGroup(self.bory)
        super().build()
        self._svg.setPos(-20, self.bory.height / 2)


class MultiChannelRelay(GraphComponent[MultiChannelData]):
    FIGURE: ClassVar[str] = "MultiChannelRelay"

    def build(self) -> None:
        self.bory = MultiChannelBory(self._data)
        self.addToGroup(self.bory)
        super().build()
        self._svg.setPos(-20, self.bory.height / 2)
