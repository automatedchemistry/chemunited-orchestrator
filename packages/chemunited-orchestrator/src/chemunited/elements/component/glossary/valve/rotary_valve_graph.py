from typing import Generic, TypeVar

import numpy as np
from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QPainterPath, QPen
from PyQt5.QtWidgets import QGraphicsItem, QGraphicsObject, QGraphicsPathItem

from chemunited.elements.component.graph_item import GraphComponent
from chemunited_core.components.live_state import rotor_links
from chemunited_core.components.valve import ValveComponentData

ValveT = TypeVar("ValveT", bound=ValveComponentData)


class RotorChannel(QGraphicsObject):
    def __init__(self, data: ValveComponentData, parent=None) -> None:
        super().__init__(parent)
        self._data = data
        self.radius = self._data.internal_radius - 14

    def boundingRect(self) -> QRectF:
        return QRectF(
            -self.radius,
            -self.radius,
            self.radius * 2,
            self.radius * 2,
        )

    @property
    def slot_count(self) -> int:
        return len(self._data.rotor_ports[0])

    def slot_point(self, slot: int) -> QPointF:
        """Where rotor slot *slot* sits: 1 is the top one, clockwise; 0 is the hub."""
        if slot == 0:
            return QPointF(0, 0)
        angle = -np.pi / 2 + (slot - 1) * 2 * np.pi / self.slot_count
        return QPointF(self.radius * np.cos(angle), self.radius * np.sin(angle))

    def paint(self, painter, option, widget=None) -> None:
        painter.setPen(QPen(Qt.GlobalColor.black, 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        # Shared with the dashboard's live view, so both draw the same rotor.
        for a, b in rotor_links(self._data):
            painter.drawLine(self.slot_point(a), self.slot_point(b))


class RotaryValveGraph(GraphComponent[ValveT], Generic[ValveT]):
    def __init__(self, data: ValveT) -> None:
        self._internal_channel: RotorChannel | None = None
        super().__init__(data)

    def build(self) -> None:
        super().build()
        self._build_internal_channels()

    def _build_internal_channels(self) -> None:
        # Stator
        for i, port in self._data.ports_by_number.items():
            r = self._data.internal_radius - 14
            if i != 0:
                x1, y1 = port.relative_position
                p1 = QPointF(x1, y1)
                d = (x1**2 + y1**2) ** 0.5
                x2 = r * (x1 / d)
                y2 = r * (y1 / d)
                p2 = QPointF(x2, y2)
                path = QPainterPath(p1)
                path.lineTo(p2)
                line = QGraphicsPathItem(path)
                self.addToGroup(line)
        # Rotor
        self._internal_channel = RotorChannel(self._data)
        self.addToGroup(self._internal_channel)

    def live_items(self) -> tuple[QGraphicsItem, ...]:
        return () if self._internal_channel is None else (self._internal_channel,)

    def live_anchors(self) -> dict[str, dict[str, object]]:
        channel = self._internal_channel
        if channel is None:
            return {}
        return {
            "rotor": {
                "center": channel.mapToScene(channel.slot_point(0)),
                "slots": [
                    channel.mapToScene(channel.slot_point(slot))
                    for slot in range(1, channel.slot_count + 1)
                ],
            }
        }

    def sync_visuals(self) -> None:
        # RotorChannel.paint() reads self._data.rotor_ports live, so a repaint
        # is all that's needed to reflect a rotor position changed elsewhere
        # (e.g. by ComponentData.apply("position", ...)).
        if self._internal_channel is not None:
            self._internal_channel.update()
        self.update()
