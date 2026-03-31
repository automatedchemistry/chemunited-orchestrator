from chemunited.shared.enums import ConnectionType
from .scene_item import SceneItem, PATTERN_DIMENSION
from typing import Callable, Optional
from PyQt5.QtGui import QPen, QColor, QBrush, QPolygonF
from PyQt5.QtCore import Qt, QPointF
from typing import ClassVar, Optional, Callable
import numpy as np
import math


class ConnectionPoint(SceneItem):
    CONNECTION_TYPE: ClassVar[ConnectionType] = ConnectionType.FLOW
    RESTING_COLOR: ClassVar[QColor] = QColor()  # overridden per subclass

    def __init__(self, position, radius=..., id_connection="1", parent=None):
        super().__init__(width=2*radius, height=2*radius, parent=parent)
        self.setPos(*position)
        self.radius = radius
        self.id_connection = id_connection
        self._evidence: bool = False
        self.update_callback: Optional[Callable] | None = None

    def _current_color(self) -> QColor:
        if self._evidence:
            return QColor("green")
        return self.RESTING_COLOR if self.RESTING_COLOR.isValid() \
            else self.colors["evidence"]

    def paint(self, painter, option, widget=None):
        painter.setPen(QPen(Qt.transparent))
        painter.setBrush(self._current_color())
        r = int(self.radius * 0.75)
        painter.drawEllipse(-r, -r, 2*r, 2*r)

    def setEvidence(self, value: bool = True) -> None:
        self._evidence = value
        if value:
            self.start_animation()
        else:
            self.stop_animation()
        self.update()

    def setCallbackPosChange(self, fn: Optional[Callable]) -> None:
        self.update_callback = fn

    def connectionMove(self) -> None:
        if self.update_callback:
            self.update_callback()


class FlowConnectionPoint(ConnectionPoint):
    CONNECTION_TYPE = ConnectionType.FLOW

    def __init__(self, position, radius=..., angle=0,
                 arc_length=np.pi*3/2, id_connection="1", parent=None):
        super().__init__(position=position, radius=radius,
                         id_connection=id_connection, parent=parent)
        self._angle = angle
        self.arc_length = arc_length

    def _on_timer(self) -> None:          # override the hook, not stop_animation
        self._angle = (self._angle + np.pi/180) % (2*np.pi)
        self.update()

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        start = int(np.degrees(self._angle) * 16)
        span  = int(np.degrees(self.arc_length) * 16)
        painter.setPen(QPen(self._current_color(), 1))
        painter.setBrush(Qt.transparent)
        painter.drawArc(-self.radius, -self.radius,
                        2*self.radius, 2*self.radius, start, span)


class HeatConnectionPoint(ConnectionPoint):
    CONNECTION_TYPE = ConnectionType.HEAT
    RESTING_COLOR = QColor("blue")

    def __init__(self, position, id_connection="1", parent=None):
        super().__init__(position=position,
                         radius=int(PATTERN_DIMENSION/15),
                         id_connection=id_connection, parent=parent)

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        arrow(painter, QPointF(-3,-3), QPointF(3,-3), QColor("#E57373"))
        arrow(painter, QPointF(3,3),  QPointF(-3,3),  QColor("#7986CB"))


class ElectronicConnectionPoint(ConnectionPoint):
    CONNECTION_TYPE = ConnectionType.ELECTRONIC
    RESTING_COLOR = QColor(Qt.darkYellow)

    def __init__(self, position, id_connection="1", parent=None):
        super().__init__(position=position,
                         radius=int(PATTERN_DIMENSION/15),
                         id_connection=id_connection, parent=parent)


class MoveConnectionPoint(ConnectionPoint):
    CONNECTION_TYPE = ConnectionType.MOVEMENT

    def __init__(self, position, id_connection="1", parent=None):
        super().__init__(position=position,
                         radius=int(PATTERN_DIMENSION/15),
                         id_connection=id_connection, parent=parent)