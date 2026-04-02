from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtGui import QPainterPath, QPen
from PyQt5.QtWidgets import QGraphicsPathItem

from chemunited.core.connections import ConnectionType, EdgeData  # noqa: F401
from chemunited.qt.draw.elements.component.component_parts.connection_point import (
    ConnectionPoint,
)


class TemporaryConnectionItem(QGraphicsPathItem):
    """Rubber-band line drawn while the user drags from an origin port."""

    def __init__(self, origin_port: ConnectionPoint) -> None:
        super().__init__()
        self._origin_port = origin_port
        pen = QPen(Qt.gray, 1, Qt.DashLine)
        self.setPen(pen)
        self.setZValue(10)

    def update_path(self, scene_pos: QPointF) -> None:
        path = QPainterPath(self._origin_port.scenePos())
        path.lineTo(scene_pos)
        self.setPath(path)
