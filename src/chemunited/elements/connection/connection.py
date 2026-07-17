import bisect
import math
from dataclasses import asdict
from typing import override

from chemunited_core.compounds import COMPOUNDS
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

_BLEND_STEP_PX = 2.0  # pixel spacing between fine color samples along the fluid column
_BLEND_MIN_SAMPLES = 24  # floor so short paths still render a smooth-looking gradient
_BLEND_MAX_SAMPLES = 400  # cap so very long paths don't trigger excessive draw calls
_BLEND_WIDTH_FRACTION = 0.03  # base blend-zone half-width, as a fraction of total path length
_BLEND_ZONE_CAP = 0.5  # a blend zone never eats more than this fraction of either adjacent pocket's span


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
        painter.setPen(self.pen())  # type: ignore
        painter.setBrush(self.brush())  # type: ignore
        painter.drawPath(self.path())  # type: ignore
        self._draw_selection(painter)

    def remove(self) -> None:
        """Detach position callbacks from both ports.

        Must be called by the orchestrator before removing this item from the scene.
        """
        self._origin_port.setCallbackPosChange(None)
        self._destination_port.setCallbackPosChange(None)


def _rgba_hex_to_qcolor(hex_str: str) -> QColor:
    h = hex_str.lstrip("#")
    return QColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(h[6:8], 16))


def _lerp_color(c1: QColor, c2: QColor, t: float) -> QColor:
    """Per-channel linear interpolation between two colors, t in [0, 1]."""
    return QColor(
        round(c1.red() + (c2.red() - c1.red()) * t),
        round(c1.green() + (c2.green() - c1.green()) * t),
        round(c1.blue() + (c2.blue() - c1.blue()) * t),
        round(c1.alpha() + (c2.alpha() - c1.alpha()) * t),
    )


def _boundary_half_widths(bounds: list[float]) -> list[float]:
    """Blend half-width for each internal boundary in *bounds*.

    Capped so a blend zone never eats more than half of either pocket it
    separates - otherwise a tiny pocket between two larger ones could be
    blended away entirely instead of still showing its own color.
    """
    widths = []
    for i in range(1, len(bounds) - 1):
        left_span = bounds[i] - bounds[i - 1]
        right_span = bounds[i + 1] - bounds[i]
        widths.append(
            min(
                _BLEND_WIDTH_FRACTION,
                left_span * _BLEND_ZONE_CAP,
                right_span * _BLEND_ZONE_CAP,
            )
        )
    return widths


def _color_at_fraction(
    t: float, bounds: list[float], colors: list[QColor], half_widths: list[float]
) -> QColor:
    """Blended color at path fraction *t*, softened near pocket boundaries."""
    n = len(colors)
    index = min(n - 1, max(0, bisect.bisect_right(bounds, t) - 1))

    if index > 0:
        boundary = bounds[index]
        half_width = half_widths[index - 1]
        if half_width > 0 and abs(t - boundary) < half_width:
            weight = 0.5 + (t - boundary) / (2 * half_width)
            return _lerp_color(colors[index - 1], colors[index], weight)
    if index < n - 1:
        boundary = bounds[index + 1]
        half_width = half_widths[index]
        if half_width > 0 and abs(t - boundary) < half_width:
            weight = 0.5 + (t - boundary) / (2 * half_width)
            return _lerp_color(colors[index], colors[index + 1], weight)
    return colors[index]


def paint_fluid_column(
    painter,
    path: QPainterPath,
    content: list,
    diameter_value: float,
    default_color: QColor,
    line_width: float,
) -> None:
    """Draw *path* as a fluid column, blended per pocket in *content*.

    Shared by any tube-shaped item (external connections, internal transport
    tubing inside Loop/FlowReactor) that needs to render recorded fluid
    content along its path. Falls back to a flat *default_color* line when
    there's no content to segment. Colors are softened across pocket
    boundaries rather than drawn as hard-edged blocks, since recorded pockets
    can be coarse (e.g. one per 1cm simulation cell) relative to a component's
    compact on-canvas size.
    """
    total_volume = sum(pocket.volume for pocket in content)
    cross_section_area = math.pi * (diameter_value / 2.0) ** 2

    if (
        not content
        or total_volume <= 0
        or cross_section_area <= 0
        or path.length() <= 0
    ):
        painter.setPen(
            QPen(
                default_color,
                line_width,
                QT_SOLID_LINE,
                QT_ROUND_CAP,
                QT_ROUND_JOIN,
            )
        )
        painter.drawPath(path)
        return

    ordered_pockets = list(reversed(content))  # content[-1]=origin-side -> path t=0
    cumulative = 0.0
    start_fraction = 0.0
    last_index = len(ordered_pockets) - 1
    bounds = [0.0]
    colors: list[QColor] = []
    for index, pocket in enumerate(ordered_pockets):
        cumulative += pocket.volume
        end_fraction = 1.0 if index == last_index else cumulative / total_volume
        if end_fraction - start_fraction > 1e-9:
            colors.append(_rgba_hex_to_qcolor(COMPOUNDS.get_color(pocket)))
            bounds.append(end_fraction)
        start_fraction = end_fraction

    if not colors:
        return
    bounds[-1] = 1.0  # guard against float drift so the last boundary reaches the path end

    half_widths = _boundary_half_widths(bounds)
    n_samples = int(
        min(
            _BLEND_MAX_SAMPLES,
            max(_BLEND_MIN_SAMPLES, round(path.length() / _BLEND_STEP_PX)),
        )
    )

    prev_point = path.pointAtPercent(0.0)
    prev_color = _color_at_fraction(0.0, bounds, colors, half_widths)
    for step in range(1, n_samples + 1):
        t = step / n_samples
        point = path.pointAtPercent(t)
        color = _color_at_fraction(t, bounds, colors, half_widths)
        painter.setPen(
            QPen(
                _lerp_color(prev_color, color, 0.5),
                line_width,
                QT_SOLID_LINE,
                QT_ROUND_CAP,
                QT_ROUND_JOIN,
            )
        )
        painter.drawLine(prev_point, point)
        prev_point = point
        prev_color = color


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

        self._draw_inner_path(painter)

        self._draw_selection(painter)

    def _draw_inner_path(self, painter) -> None:
        """Draw the fluid column, segmented per pocket when content volumes are known."""
        content = [] if self.inf.air_pressure_line else self.inf.content
        paint_fluid_column(
            painter,
            self.path(),
            content,
            self.inf.diameter_value,
            self._inner_color,
            self._inner_width,
        )


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
