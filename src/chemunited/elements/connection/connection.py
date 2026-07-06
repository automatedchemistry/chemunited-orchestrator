from dataclasses import asdict
from typing import override

from chemunited_core.connections import ConnectionType, EdgeData, EdgeMode
from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtGui import QColor, QPainterPath, QPen
from PyQt5.QtWidgets import QGraphicsItem

from chemunited.elements.component.component_parts.connection_point import (
    ConnectionPoint,
)
from chemunited.shared.enums import SetupStepMode
from chemunited.shared.graph_objects import MovablePathItem, PathElementItem

QT_DASH_LINE = getattr(Qt, "DashLine")
QT_ROUND_CAP = getattr(Qt, "RoundCap")
QT_ROUND_JOIN = getattr(Qt, "RoundJoin")
QT_SOLID_LINE = getattr(Qt, "SolidLine")


class TemporaryConnectionItem(PathElementItem):
    """Rubber-band line drawn while the user drags from an origin port."""

    DEFAULT_COLOR: QColor = QColor("black")
    DEFAULT_LINE_WIDTH: float = 1
    DEFAULT_PATH_STYLE = QT_DASH_LINE

    def __init__(self, origin_port: ConnectionPoint) -> None:
        super().__init__()
        self._origin_port = origin_port
        self.setZValue(10)

    def update_path(self, scene_pos: QPointF) -> None:
        path = QPainterPath(self._origin_port.scenePos())
        path.lineTo(scene_pos)
        self.setPath(path)


class BaseConnectionItem(MovablePathItem):
    """Represents a connection between two components."""

    CATEGORY: ConnectionType

    def __init__(
        self,
        origin_port: ConnectionPoint,
        destination_port: ConnectionPoint,
        data: EdgeData,
    ) -> None:
        # _data must be set before super().__init__ because MovablePathItem
        # calls rebuild_path() during construction, which accesses self._data.
        self._data = data
        self._origin_port = origin_port
        self._destination_port = destination_port
        p1 = origin_port.scenePos()
        p2 = destination_port.scenePos()
        super().__init__(
            (p1.x(), p1.y()),
            (p2.x(), p2.y()),
            inflection_points=data.inflection_points,
        )
        self.setZValue(10)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)  # type: ignore
        self._attach_ports()
        self.setStraight(data.straight_path)

    def _attach_ports(self) -> None:
        self._origin_port.setCallbackPosChange(self.rebuild_path)
        self._destination_port.setCallbackPosChange(self.rebuild_path)

    @property
    def inf(self) -> EdgeData:
        return self._data

    @property
    def base_mode_instance(self) -> EdgeMode:
        self._sync_path_data()
        data = asdict(self._data)
        mode_data = {
            name: value for name, value in data.items() if name in EdgeMode.model_fields
        }
        return EdgeMode.model_validate(mode_data)

    def sync(self, mode: EdgeMode) -> None:
        self._data.update(mode)

    def _sync_path_data(self) -> None:
        p1 = self._origin_port.scenePos()
        p2 = self._destination_port.scenePos()
        self._origin = [p1.x(), p1.y()]
        self._end = [p2.x(), p2.y()]
        self._data.inflection_points = [
            (point[0], point[1]) for point in self._inflection_points
        ]

    @override
    def rebuild_path(self) -> None:
        self._sync_path_data()
        super().rebuild_path()

    @override
    def setStraight(self, value: bool) -> None:
        # Update the data with the current straight path value
        self._data.straight_path = value
        super().setStraight(value)

    def set_frame_mode(self, mode: SetupStepMode) -> None:
        """
        Visibility rules per mode:

        +--------------+---------+-----------+--------+
        | mode         | visible | _handles  | path   |
        +==============+=========+===========+========+
        | DESIGN       | yes     | yes       | yes    |
        | PROTOCOLS    | yes     | no        | yes    |
        | CONNECTIVITY | yes     | no        | no     |
        +--------------+---------+-----------+--------+
        """
        if mode == SetupStepMode.CONNECTIVITY:
            self.hide()
        else:
            self.show()

        if mode != SetupStepMode.DESIGN:
            for p in self._handles:
                p.hide()
        else:
            for p in self._handles:
                p.show()
        self.rebuild_path()

    def _draw_selection(self, painter) -> None:
        """Draw a blue dashed overlay when the connection is selected."""
        if not self.isSelected():
            return
        pen = QPen(QColor("#1E88E5"), 4.0, QT_DASH_LINE)
        pen.setCapStyle(QT_ROUND_CAP)
        pen.setJoinStyle(QT_ROUND_JOIN)
        painter.setPen(pen)
        painter.drawPath(self.path())

    def paint(self, painter, option, widget=None):
        painter.setPen(self.pen())
        painter.setBrush(self.brush())
        painter.drawPath(self.path())
        self._draw_selection(painter)

    def remove(self) -> None:
        """Detach position callbacks from both ports.

        Must be called by the orchestrator before removing this item from the scene.
        """
        self._origin_port.setCallbackPosChange(None)
        self._destination_port.setCallbackPosChange(None)


class HydraulicConnectionItem(BaseConnectionItem):
    """Represents a Hydraulic connection between two components."""

    DEFAULT_OUTER_COLOR: QColor = QColor("#555555")  # tube wall
    DEFAULT_INNER_COLOR: QColor = QColor("#aaddff")  # fluid
    AIR_INNER_COLOR: QColor = QColor("#aaaaaa")  # air / pneumatic
    DEFAULT_OUTER_WIDTH: float = 5.0
    DEFAULT_INNER_WIDTH: float = 3.0
    CATEGORY: ConnectionType = ConnectionType.HYDRAULIC

    def __init__(
        self,
        origin_port: ConnectionPoint,
        destination_port: ConnectionPoint,
        data: EdgeData,
    ) -> None:
        super().__init__(origin_port, destination_port, data)
        self._outer_color = self.DEFAULT_OUTER_COLOR
        self._inner_color = self.DEFAULT_INNER_COLOR
        self._outer_width = self.DEFAULT_OUTER_WIDTH
        self._inner_width = self.DEFAULT_INNER_WIDTH
        if data.air_pressure_line:
            self.set_air_pressure_line(True)

    def set_air_pressure_line(self, value: bool) -> None:
        self._data.air_pressure_line = value
        if value:
            self._inner_width = 1
            self._outer_width = 3
            self._inner_color = QColor("#aaaaaa")
            self._outer_color = QColor(100, 100, 100)
        else:
            self._inner_width = self.DEFAULT_INNER_WIDTH
            self._outer_width = self.DEFAULT_OUTER_WIDTH
            self._inner_color = self.DEFAULT_INNER_COLOR
            self._outer_color = self.DEFAULT_OUTER_COLOR
        self.update()

    def paint(self, painter, option, widget=None):
        painter.setPen(
            QPen(
                self._outer_color,
                self._outer_width,
                QT_SOLID_LINE,
                QT_ROUND_CAP,
                QT_ROUND_JOIN,
            )
        )
        painter.drawPath(self.path())

        painter.setPen(
            QPen(
                self._inner_color,
                self._inner_width,
                QT_SOLID_LINE,
                QT_ROUND_CAP,
                QT_ROUND_JOIN,
            )
        )
        painter.drawPath(self.path())
        self._draw_selection(painter)


class HeatConnectionItem(BaseConnectionItem):
    """Represents a heat connection between two components."""

    DEFAULT_COLOR: QColor = QColor("red")
    DEFAULT_LINE_WIDTH: float = 2
    DEFAULT_PATH_STYLE = QT_DASH_LINE
    CATEGORY: ConnectionType = ConnectionType.HEAT


class ElectricalConnectionItem(BaseConnectionItem):
    """Represents an electrical connection between two components."""

    DEFAULT_COLOR: QColor = QColor("green")
    DEFAULT_LINE_WIDTH: float = 2
    DEFAULT_PATH_STYLE = QT_DASH_LINE
    CATEGORY: ConnectionType = ConnectionType.ELECTRONIC


class MovementConnectionItem(BaseConnectionItem):
    """Represents a movement connection between two components."""

    DEFAULT_COLOR: QColor = QColor("blue")
    DEFAULT_LINE_WIDTH: float = 2
    DEFAULT_PATH_STYLE = QT_DASH_LINE
    CATEGORY: ConnectionType = ConnectionType.MOVEMENT
