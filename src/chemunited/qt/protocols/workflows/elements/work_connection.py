import math
from collections.abc import Sequence
from enum import Enum
from typing import Callable, TypedDict, cast

from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtGui import QBrush, QColor, QFont, QPainterPath, QPen
from PyQt5.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsTextItem,
)

from .access_point import WorkflowAccessPoints


class CurveAttachedPosition(Enum):
    RIGHT = 1
    LEFT = 2
    TOP = 3
    BOTTOM = 4
    VERTICAL = 5


class ConnectionConfig(TypedDict):
    start: CurveAttachedPosition
    end: CurveAttachedPosition
    arrow: bool


class WorkflowConnection(QGraphicsPathItem):
    MAX_INFLECTION_POINTS = 2
    CORNER_RADIUS = 18.0
    START_LEAD_DISTANCE = 32.0
    NORMAL_COLOR = QColor("#2563EB")
    CONDITIONAL_FALSE_COLOR = QColor("#D97706")
    LOOPBACK_COLOR = QColor("#7C3AED")

    def __init__(
        self,
        start_item: WorkflowAccessPoints,
        end_item: WorkflowAccessPoints,
        inflection_points: list[tuple[float, float] | QPointF] | None = None,
        bend_point: tuple[float, float] | QPointF | None = None,
        edge_data: dict | None = None,
        on_geometry_changed: Callable[["WorkflowConnection"], None] | None = None,
    ):
        super().__init__()
        self.start_item = start_item
        self.end_item = end_item
        self.edge_data = dict(edge_data or {})
        self._on_geometry_changed = on_geometry_changed
        self.config: ConnectionConfig = {
            "start": self._curve_position(start_item.role),
            "end": CurveAttachedPosition.LEFT,
            "arrow": True,
        }
        self.inflection_points = self._coerce_inflection_points(
            inflection_points=inflection_points,
            bend_point=bend_point,
        )
        self._default_width = 2
        self._selected_width = 3
        self._selected_color = QColor("#3A7AFE")
        self._curve_path = QPainterPath()
        self._route_waypoints: list[QPointF] = []
        self.start_node = start_item.node.node_name if start_item.node else ""
        self.end_node = end_item.node.node_name if end_item.node else ""
        self.start_role = str(self.edge_data.get("start_role", start_item.role))
        self.edge_data.setdefault("start_role", self.start_role)
        self.label_item = QGraphicsTextItem(self)
        label_font = QFont("Segoe UI", 8)
        self.label_item.setFont(label_font)
        self.label_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.label_item.setDefaultTextColor(self._semantic_color())
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self._apply_style()
        self.setZValue(-0.5)
        self._inflection_handles = [
            WorkflowInflectionHandle(self, 0),
            WorkflowInflectionHandle(self, 1),
        ]
        self.updateConnection()

    @staticmethod
    def _curve_position(role: str) -> CurveAttachedPosition:
        if role == "top":
            return CurveAttachedPosition.TOP
        if role == "bottom":
            return CurveAttachedPosition.BOTTOM
        return CurveAttachedPosition.RIGHT

    def _apply_style(self, selected: bool = False):
        pen = self.pen()
        color = self._semantic_color()
        if selected:
            color = color.lighter(120)
        pen.setColor(color)
        pen.setWidth(self._selected_width if selected else self._default_width)
        pen.setStyle(
            Qt.PenStyle.DashLine
            if self.edge_data.get("loopback") is True
            else Qt.PenStyle.SolidLine
        )
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        self.setPen(pen)
        self.label_item.setDefaultTextColor(color)

    def _semantic_color(self) -> QColor:
        if self.edge_data.get("loopback") is True:
            return QColor(self.LOOPBACK_COLOR)
        if self.edge_data.get("condition") is False:
            return QColor(self.CONDITIONAL_FALSE_COLOR)
        return QColor(self.NORMAL_COLOR)

    def _edge_label_text(self) -> str:
        raw_label = self.edge_data.get("label")
        label = str(raw_label).strip() if raw_label is not None else ""
        if self.edge_data.get("loopback") is True:
            parts = [
                "loopback=True",
                f"trigger_on={str(bool(self.edge_data.get('trigger_on', False))).lower()}",
            ]
            max_iterations = self.edge_data.get("max_iterations")
            if max_iterations is not None:
                parts.append(f"max_iterations={max_iterations}")
        else:
            parts = [
                f"condition={str(bool(self.edge_data.get('condition', True))).lower()}"
            ]

        metadata_text = " | ".join(parts)
        return f"{label}\n{metadata_text}" if label else metadata_text

    @staticmethod
    def _coerce_point(point: tuple[float, float] | QPointF) -> QPointF:
        if isinstance(point, tuple):
            return QPointF(*point)
        return QPointF(point)

    def _coerce_inflection_points(
        self,
        inflection_points: Sequence[tuple[float, float] | QPointF] | None,
        bend_point: tuple[float, float] | QPointF | None,
    ) -> list[QPointF]:
        if inflection_points:
            return [
                self._coerce_point(point)
                for point in inflection_points[: self.MAX_INFLECTION_POINTS]
            ]
        if bend_point is not None:
            return [self._coerce_point(bend_point)]
        return []

    @property
    def bend_point(self) -> QPointF | None:
        return self.inflection_points[0] if self.inflection_points else None

    def _anchor_point(
        self, item: WorkflowAccessPoints, position: CurveAttachedPosition
    ) -> QPointF:
        rect = item.sceneBoundingRect()
        if position == CurveAttachedPosition.RIGHT:
            return QPointF(rect.right(), rect.center().y())
        if position == CurveAttachedPosition.LEFT:
            return QPointF(rect.left(), rect.center().y())
        if position == CurveAttachedPosition.TOP:
            return QPointF(rect.center().x(), rect.top())
        if position == CurveAttachedPosition.BOTTOM:
            return QPointF(rect.center().x(), rect.bottom())
        return rect.center()

    @staticmethod
    def _is_close(value_a: float, value_b: float, tolerance: float = 0.25) -> bool:
        return math.isclose(value_a, value_b, abs_tol=tolerance)

    @classmethod
    def _same_point(cls, point_a: QPointF, point_b: QPointF) -> bool:
        return cls._is_close(point_a.x(), point_b.x()) and cls._is_close(
            point_a.y(), point_b.y()
        )

    @classmethod
    def _is_collinear(
        cls, point_a: QPointF, point_b: QPointF, point_c: QPointF
    ) -> bool:
        same_x = cls._is_close(point_a.x(), point_b.x()) and cls._is_close(
            point_b.x(), point_c.x()
        )
        same_y = cls._is_close(point_a.y(), point_b.y()) and cls._is_close(
            point_b.y(), point_c.y()
        )
        return same_x or same_y

    @staticmethod
    def _segment_length(point_a: QPointF, point_b: QPointF) -> float:
        return math.hypot(point_b.x() - point_a.x(), point_b.y() - point_a.y())

    @classmethod
    def _segment_direction(cls, point_a: QPointF, point_b: QPointF) -> QPointF:
        length = cls._segment_length(point_a, point_b)
        if length == 0:
            return QPointF(0, 0)
        return QPointF(
            (point_b.x() - point_a.x()) / length,
            (point_b.y() - point_a.y()) / length,
        )

    @staticmethod
    def _direction_vector(position: CurveAttachedPosition) -> QPointF:
        if position == CurveAttachedPosition.RIGHT:
            return QPointF(1, 0)
        if position == CurveAttachedPosition.LEFT:
            return QPointF(-1, 0)
        if position == CurveAttachedPosition.TOP:
            return QPointF(0, -1)
        if position == CurveAttachedPosition.BOTTOM:
            return QPointF(0, 1)
        return QPointF(0, 1)

    def _start_lead_point(self, start_anchor: QPointF) -> QPointF:
        direction = self._direction_vector(self.config["start"])
        return QPointF(
            start_anchor.x() + direction.x() * self.START_LEAD_DISTANCE,
            start_anchor.y() + direction.y() * self.START_LEAD_DISTANCE,
        )

    @classmethod
    def _segment_points(
        cls, start_point: QPointF, end_point: QPointF, *, horizontal_first: bool
    ) -> list[QPointF]:
        points = [QPointF(start_point)]
        if cls._same_point(start_point, end_point):
            return points
        if cls._is_close(start_point.x(), end_point.x()) or cls._is_close(
            start_point.y(), end_point.y()
        ):
            points.append(QPointF(end_point))
            return points
        elbow = (
            QPointF(end_point.x(), start_point.y())
            if horizontal_first
            else QPointF(start_point.x(), end_point.y())
        )
        points.extend([elbow, QPointF(end_point)])
        return points

    @staticmethod
    def _mid_x(point_a: QPointF, point_b: QPointF) -> float:
        return (point_a.x() + point_b.x()) / 2

    def _tail_waypoints(
        self, start_point: QPointF, end_anchor: QPointF
    ) -> list[QPointF]:
        trunk_x = self._mid_x(start_point, end_anchor)
        return [
            QPointF(start_point),
            QPointF(trunk_x, start_point.y()),
            QPointF(trunk_x, end_anchor.y()),
            QPointF(end_anchor),
        ]

    def _default_auto_waypoints(
        self, start_anchor: QPointF, end_anchor: QPointF
    ) -> list[QPointF]:
        if self.config["start"] == CurveAttachedPosition.RIGHT:
            return self._tail_waypoints(start_anchor, end_anchor)
        lead_point = self._start_lead_point(start_anchor)
        trunk_x = self._mid_x(lead_point, end_anchor)
        return [
            QPointF(start_anchor),
            lead_point,
            QPointF(trunk_x, lead_point.y()),
            QPointF(trunk_x, end_anchor.y()),
            QPointF(end_anchor),
        ]

    def _guided_waypoints(
        self,
        start_anchor: QPointF,
        end_anchor: QPointF,
        guides: list[QPointF],
    ) -> list[QPointF]:
        points = [QPointF(start_anchor)]
        current = QPointF(start_anchor)

        if self.config["start"] in {
            CurveAttachedPosition.TOP,
            CurveAttachedPosition.BOTTOM,
        }:
            current = self._start_lead_point(start_anchor)
            points.append(current)

        first_guide = QPointF(guides[0])
        points.extend(
            self._segment_points(current, first_guide, horizontal_first=True)[1:]
        )

        previous_guide = first_guide
        for guide in guides[1:]:
            next_guide = QPointF(guide)
            points.extend(
                self._segment_points(previous_guide, next_guide, horizontal_first=True)[
                    1:
                ]
            )
            previous_guide = next_guide

        points.extend(self._tail_waypoints(previous_guide, end_anchor)[1:])
        return points

    def _normalize_waypoints(self, points: list[QPointF]) -> list[QPointF]:
        deduplicated: list[QPointF] = []
        for point in points:
            candidate = QPointF(point)
            if not deduplicated or not self._same_point(deduplicated[-1], candidate):
                deduplicated.append(candidate)

        normalized: list[QPointF] = []
        for point in deduplicated:
            if len(normalized) >= 2 and self._is_collinear(
                normalized[-2], normalized[-1], point
            ):
                normalized[-1] = point
            else:
                normalized.append(point)
        return normalized

    def _route_waypoints_from_anchors(
        self, start_anchor: QPointF, end_anchor: QPointF
    ) -> list[QPointF]:
        raw_points = (
            self._guided_waypoints(start_anchor, end_anchor, self.inflection_points)
            if self.inflection_points
            else self._default_auto_waypoints(start_anchor, end_anchor)
        )
        return self._normalize_waypoints(raw_points)

    def orthogonal_waypoints(self) -> list[QPointF]:
        return [QPointF(point) for point in self._route_waypoints]

    def _default_inflection_point(self, index: int = 0) -> QPointF:
        start_anchor = self._anchor_point(self.start_item, self.config["start"])
        end_anchor = self._anchor_point(self.end_item, self.config["end"])
        if index == 1 and self.inflection_points:
            first = self.inflection_points[0]
            trunk_x = self._mid_x(first, end_anchor)
            return QPointF(trunk_x, (first.y() + end_anchor.y()) / 2)

        if self.config["start"] == CurveAttachedPosition.RIGHT:
            start_for_guide = start_anchor
        else:
            start_for_guide = self._start_lead_point(start_anchor)
        trunk_x = self._mid_x(start_for_guide, end_anchor)
        return QPointF(trunk_x, (start_for_guide.y() + end_anchor.y()) / 2)

    def _rounded_path_from_waypoints(self, waypoints: list[QPointF]) -> QPainterPath:
        path = QPainterPath()
        if not waypoints:
            return path
        path.moveTo(waypoints[0])
        if len(waypoints) == 1:
            return path

        for index in range(1, len(waypoints) - 1):
            previous_point = waypoints[index - 1]
            corner_point = waypoints[index]
            next_point = waypoints[index + 1]
            incoming_length = self._segment_length(previous_point, corner_point)
            outgoing_length = self._segment_length(corner_point, next_point)
            corner_radius = min(
                self.CORNER_RADIUS,
                incoming_length / 2,
                outgoing_length / 2,
            )
            if corner_radius <= 0:
                path.lineTo(corner_point)
                continue

            incoming_direction = self._segment_direction(previous_point, corner_point)
            outgoing_direction = self._segment_direction(corner_point, next_point)
            entry_point = QPointF(
                corner_point.x() - incoming_direction.x() * corner_radius,
                corner_point.y() - incoming_direction.y() * corner_radius,
            )
            exit_point = QPointF(
                corner_point.x() + outgoing_direction.x() * corner_radius,
                corner_point.y() + outgoing_direction.y() * corner_radius,
            )
            path.lineTo(entry_point)
            path.quadTo(corner_point, exit_point)

        path.lineTo(waypoints[-1])
        return path

    def _draw_arrow(self, path: QPainterPath, tip: QPointF, previous: QPointF):
        if not self.config["arrow"]:
            return

        delta_x = tip.x() - previous.x()
        delta_y = tip.y() - previous.y()
        distance = (delta_x**2 + delta_y**2) ** 0.5
        if distance == 0:
            return

        unit_x = delta_x / distance
        unit_y = delta_y / distance
        arrow_size = 12
        wing_size = 6
        base = QPointF(
            tip.x() - unit_x * arrow_size,
            tip.y() - unit_y * arrow_size,
        )
        perpendicular = QPointF(-unit_y, unit_x)
        left_wing = QPointF(
            base.x() + perpendicular.x() * wing_size,
            base.y() + perpendicular.y() * wing_size,
        )
        right_wing = QPointF(
            base.x() - perpendicular.x() * wing_size,
            base.y() - perpendicular.y() * wing_size,
        )

        path.moveTo(tip)
        path.lineTo(left_wing)
        path.moveTo(tip)
        path.lineTo(right_wing)

    def _update_path_from_points(self):
        start_anchor = self._anchor_point(self.start_item, self.config["start"])
        end_anchor = self._anchor_point(self.end_item, self.config["end"])
        self._route_waypoints = self._route_waypoints_from_anchors(
            start_anchor, end_anchor
        )
        curve_path = self._rounded_path_from_waypoints(self._route_waypoints)
        self._curve_path = curve_path
        path = QPainterPath(curve_path)
        tip = QPointF(self._route_waypoints[-1])
        previous = (
            QPointF(self._route_waypoints[-2])
            if len(self._route_waypoints) > 1
            else QPointF(tip.x() - 1, tip.y())
        )
        self._draw_arrow(path, tip, previous)
        self.setPath(path)
        self._update_label_position()

    def _update_label_position(self):
        self.label_item.setPlainText(self._edge_label_text())
        if self._curve_path.isEmpty():
            return
        midpoint = self._curve_path.pointAtPercent(0.5)
        angle = self._curve_path.angleAtPercent(0.5)
        radians = math.radians(angle)
        normal = QPointF(-math.sin(radians), -math.cos(radians))
        if self.start_role == "bottom":
            normal = QPointF(-normal.x(), -normal.y())

        label_rect = self.label_item.boundingRect()
        offset_distance = 22.0
        label_center = QPointF(
            midpoint.x() + normal.x() * offset_distance,
            midpoint.y() + normal.y() * offset_distance,
        )
        self.label_item.setPos(
            label_center.x() - label_rect.width() / 2,
            label_center.y() - label_rect.height() / 2,
        )

    def _update_handle_positions(self):
        for index, handle in enumerate(self._inflection_handles):
            if index < len(self.inflection_points):
                handle.sync_to(self.inflection_points[index])
            else:
                handle.sync_to(self._default_inflection_point(index))

    def _update_handle_visibility(self):
        for index, handle in enumerate(self._inflection_handles):
            is_primary = index == 0
            handle.setVisible(
                self.isSelected()
                and (is_primary or index < len(self.inflection_points))
            )

    def sync_from_model(self, edge_data: dict[str, object]):
        self.edge_data = dict(edge_data)
        self.start_role = str(self.edge_data.get("start_role", self.start_role))
        inflection_points = cast(
            Sequence[tuple[float, float] | QPointF] | None,
            edge_data.get("inflection_points"),
        )
        self.set_inflection_points(
            inflection_points,
            persist=False,
        )
        self._apply_style(self.isSelected())

    def set_inflection_points(
        self,
        points: Sequence[tuple[float, float] | QPointF] | None,
        persist: bool = True,
    ):
        self.inflection_points = self._coerce_inflection_points(
            inflection_points=points,
            bend_point=None,
        )
        self.updateConnection()
        if persist and self._on_geometry_changed is not None:
            self._on_geometry_changed(self)

    def set_inflection_point(
        self,
        index: int,
        point: tuple[float, float] | QPointF,
        persist: bool = True,
    ):
        points = list(self.inflection_points)
        while len(points) <= index and len(points) < self.MAX_INFLECTION_POINTS:
            points.append(self._default_inflection_point(len(points)))
        if index < len(points):
            points[index] = self._coerce_point(point)
        self.set_inflection_points(points, persist=persist)

    def add_inflection_point(self, point: tuple[float, float] | QPointF | None = None):
        if isinstance(point, bool):
            point = None
        if len(self.inflection_points) >= self.MAX_INFLECTION_POINTS:
            return
        if point is None:
            point = self._default_inflection_point(len(self.inflection_points))
        self.set_inflection_points([*self.inflection_points, point])

    def remove_last_inflection_point(self):
        if not self.inflection_points:
            return
        self.set_inflection_points(self.inflection_points[:-1])

    def set_bend_point(
        self, bend_point: tuple[float, float] | QPointF | None, persist: bool = True
    ):
        if bend_point is None:
            self.set_inflection_points([], persist=persist)
            return
        self.set_inflection_point(0, bend_point, persist=persist)

    def clear_bend_point(self):
        self.clear_inflection_points()

    def clear_inflection_points(self):
        self.set_inflection_points([])

    def updateConnection(self):
        self._update_path_from_points()
        self._update_handle_positions()
        self._update_handle_visibility()

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self._apply_style(bool(value))
            self._update_handle_visibility()
        return super().itemChange(change, value)


class WorkflowInflectionHandle(QGraphicsEllipseItem):
    def __init__(self, connection: WorkflowConnection, index: int, radius: int = 6):
        super().__init__(-radius, -radius, radius * 2, radius * 2, connection)
        self.connection = connection
        self.index = index
        self._syncing = False
        self.setBrush(QBrush(connection._selected_color))
        self.setPen(QPen(QColor("#FFFFFF"), 1.2))
        self.setZValue(2)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        flags = cast(
            QGraphicsItem.GraphicsItemFlags,
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges,
        )
        self.setFlags(flags)
        self.setVisible(False)

    def sync_to(self, scene_pos: QPointF):
        self._syncing = True
        self.setPos(scene_pos)
        self._syncing = False

    def mousePressEvent(self, event):
        self.connection.setSelected(True)
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)

    def itemChange(self, change, value):
        if (
            change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged
            and not self._syncing
        ):
            self.connection.set_inflection_point(
                self.index,
                self.connection.mapToScene(value),
            )
        return super().itemChange(change, value)
