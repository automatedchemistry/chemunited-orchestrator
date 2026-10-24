from typing import ClassVar

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QBrush, QColor, QPen
from PyQt5.QtWidgets import QGraphicsItem

from chemunited.elements.component.component_parts import SceneItem
from chemunited.elements.component.graph_item import GraphComponent
from chemunited_core.figure_registry.technical import MultiChannelData

LIGHT_RADIUS = 4


class MultiChannelBory(SceneItem):
    def __init__(self, data: "MultiChannelData") -> None:
        self._data = data
        super().__init__(width=15, height=16 * data.channels + 4)
        self.lights = MultiChannelLights(self, data)

    def light_center(self, channel: int) -> QPointF:
        """Centre of the light for 0-based *channel*, in this item's coordinates."""
        return QPointF(0, -self.height / 2 + channel * 16 + 4 + LIGHT_RADIUS)

    def paint(self, painter, option, widget=None) -> None:
        painter.setPen(QPen(Qt.GlobalColor.black, 1))
        painter.setBrush(QBrush(Qt.GlobalColor.white))
        painter.drawRect(self.boundingRect())


class MultiChannelLights(QGraphicsItem):
    """One light per channel, drawn over the body."""

    def __init__(self, body: MultiChannelBory, data: MultiChannelData) -> None:
        super().__init__(body)
        self._body = body
        self._data = data

    def boundingRect(self) -> QRectF:
        return self._body.boundingRect()

    def paint(self, painter, option, widget=None) -> None:
        painter.setPen(QPen(Qt.GlobalColor.black, 1))
        painter.setBrush(QBrush(Qt.GlobalColor.white))
        value = self._data.active
        r = LIGHT_RADIUS
        for i in range(self._data.channels):
            if value:
                color = QColor("#8BC34A") if value[i] else QColor("#E8F5E9")
                painter.setPen(QPen(color, 2))
            painter.drawEllipse(self._body.light_center(i), r, r)


class _MultiChannelGraph(GraphComponent[MultiChannelData]):
    def build(self) -> None:
        self.bory = MultiChannelBory(self._data)
        self.addToGroup(self.bory)
        super().build()
        self._svg.setPos(-20, self.bory.height / 2)

    def figure_box(self) -> QRectF:
        return super().figure_box().united(self.bory.sceneBoundingRect())


class MultiChannelADC(_MultiChannelGraph):
    FIGURE: ClassVar[str] = "MultiChannelADC"


class MultiChannelDAC(_MultiChannelGraph):
    FIGURE: ClassVar[str] = "MultiChannelDAC"


class MultiChannelRelay(_MultiChannelGraph):
    FIGURE: ClassVar[str] = "MultiChannelRelay"

    def sync_visuals(self) -> None:
        # The lights read the channel states live; a repaint shows a command.
        self.bory.lights.update()

    def live_items(self) -> tuple[QGraphicsItem, ...]:
        return (self.bory.lights,)

    def live_anchors(self) -> dict[str, dict[str, object]]:
        return {
            "lights": {
                "points": [
                    self.bory.mapToScene(self.bory.light_center(i))
                    for i in range(self._data.channels)
                ],
                "r": float(LIGHT_RADIUS),
            }
        }
