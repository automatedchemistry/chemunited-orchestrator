from typing import Generic, TypeVar

import numpy as np
from chemunited_core.components.valve import ValveComponentData
from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QPainterPath, QPen
from PyQt5.QtWidgets import QGraphicsObject, QGraphicsPathItem

from chemunited.elements.component.graph_item import GraphComponent

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

    def paint(self, painter, option, widget=None) -> None:
        painter.setPen(QPen(Qt.GlobalColor.black, 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        rotor_ports = [list(row) for row in self._data.rotor_ports]
        angles = np.arange(-np.pi / 2, 3 * np.pi / 2, 2 * np.pi / len(rotor_ports[0]))
        if 0 in self._data.ports_by_number:
            for i, value in enumerate(self._data.rotor_ports[0]):
                if value == self._data.rotor_ports[1][0]:
                    rotor_ports[0][i] = None
                    x2, y2 = (
                        self.radius * np.cos(angles[i]),
                        self.radius * np.sin(angles[i]),
                    )
                    painter.drawLine(QPointF(0, 0), QPointF(x2, y2))
        for i, value in enumerate(self._data.rotor_ports[0]):
            if value:
                for j, value_2 in enumerate(rotor_ports[0]):
                    if value == value_2 and j != i:
                        x1, y1 = (
                            self.radius * np.cos(angles[i]),
                            self.radius * np.sin(angles[i]),
                        )
                        x2, y2 = (
                            self.radius * np.cos(angles[j]),
                            self.radius * np.sin(angles[j]),
                        )
                        painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))
                        break


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

    def sync_visuals(self) -> None:
        # RotorChannel.paint() reads self._data.rotor_ports live, so a repaint
        # is all that's needed to reflect a rotor position changed elsewhere
        # (e.g. by ComponentData.apply("position", ...)).
        if self._internal_channel is not None:
            self._internal_channel.update()
        self.update()
