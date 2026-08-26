from PyQt5.QtCore import Qt
from PyQt5.QtGui import QBrush, QColor, QPainterPath, QPen
from PyQt5.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsPathItem,
)

from chemunited.utils.math_functions import build_smooth_path, build_straight_path

QT_ROUND_CAP = getattr(Qt, "RoundCap")
QT_ROUND_JOIN = getattr(Qt, "RoundJoin")
QT_SIZE_ALL_CURSOR = getattr(Qt, "SizeAllCursor")
QT_SOLID_LINE = getattr(Qt, "SolidLine")
QGRAPHICS_ITEM_IS_MOVABLE = getattr(QGraphicsItem, "ItemIsMovable")
QGRAPHICS_ITEM_IS_SELECTABLE = getattr(QGraphicsItem, "ItemIsSelectable")
QGRAPHICS_ITEM_POSITION_HAS_CHANGED = getattr(QGraphicsItem, "ItemPositionHasChanged")
QGRAPHICS_ITEM_SENDS_GEOMETRY_CHANGES = getattr(
    QGraphicsItem,
    "ItemSendsGeometryChanges",
)


class PathElementItem(QGraphicsPathItem):

    DEFAULT_COLOR: QColor = QColor("black")
    DEFAULT_LINE_WIDTH: float = 2.0
    DEFAULT_PATH_STYLE = QT_SOLID_LINE

    def __init__(self, parent=None):
        super().__init__(parent)
        self._color: QColor = self.DEFAULT_COLOR
        self._line_width: float = self.DEFAULT_LINE_WIDTH
        self._path_style = self.DEFAULT_PATH_STYLE
        self._update_pen()

    def _update_pen(self) -> None:
        pen = QPen(self._color, self._line_width)
        pen.setCapStyle(QT_ROUND_CAP)
        pen.setJoinStyle(QT_ROUND_JOIN)
        if self._path_style:
            pen.setStyle(self._path_style)
        self.setPen(pen)

    @property
    def color(self) -> QColor:
        return self._color

    @color.setter
    def color(self, value: QColor) -> None:
        self._color = value
        self._update_pen()

    @property
    def line_width(self) -> float:
        return self._line_width

    @line_width.setter
    def line_width(self, value: float) -> None:
        self._line_width = value
        self._update_pen()

    @property
    def path_style(self):
        return self._path_style

    @path_style.setter
    def path_style(self, value):
        self._path_style = value
        self.rebuild_path()

    def rebuild_path(self) -> None:
        """Override in subclass to build the QPainterPath."""
        raise NotImplementedError


class DraggablePoint(QGraphicsEllipseItem):

    RADIUS: float = 6.0

    def __init__(self, x: float, y: float, callback=None, parent=None):
        r = self.RADIUS
        super().__init__(-r, -r, r * 2, r * 2, parent)
        self.setPos(x, y)
        self.setFlags(
            QGRAPHICS_ITEM_IS_MOVABLE
            | QGRAPHICS_ITEM_SENDS_GEOMETRY_CHANGES
            | QGRAPHICS_ITEM_IS_SELECTABLE
        )
        self.setBrush(QBrush(QColor("white")))
        self.setPen(QPen(QColor("#3a86ff"), 2.0))
        self.setCursor(QT_SIZE_ALL_CURSOR)
        self._callback = callback

    def itemChange(self, change, value):
        if change == QGRAPHICS_ITEM_POSITION_HAS_CHANGED and self._callback:
            self._callback()
        return super().itemChange(change, value)


class MovablePathItem(PathElementItem):

    def __init__(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
        inflection_points: list[tuple[float, float]] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._origin: list[float] = list(origin)
        self._end: list[float] = list(destination)
        self._inflection_points: list[list[float]] = [
            list(p) for p in (inflection_points or [])
        ]
        self._straight: bool = True
        self._handles: list[DraggablePoint] = []
        self._sync_handles()
        self.rebuild_path()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _all_points(self) -> list[list[float]]:
        return [self._origin] + self._inflection_points + [self._end]

    def _sync_handles(self) -> None:
        """Recreate handle items to match the current inflection points only."""
        for handle in self._handles:
            handle.setParentItem(None)
        self._handles.clear()
        for pt in self._inflection_points:
            handle = DraggablePoint(
                pt[0], pt[1], callback=self._on_handle_moved, parent=self
            )
            self._handles.append(handle)

    def _on_handle_moved(self) -> None:
        """Called by any DraggablePoint when it is dragged."""
        self._inflection_points = [[h.pos().x(), h.pos().y()] for h in self._handles]
        self.rebuild_path()

    def _build_painter_path(self) -> None:
        """Convert the current point list to a QPainterPath and apply it."""
        pts = self._all_points()
        arr = build_straight_path(pts) if self._straight else build_smooth_path(pts)
        path = QPainterPath()
        path.moveTo(arr[0][0], arr[0][1])
        for pt in arr[1:]:
            path.lineTo(pt[0], pt[1])
        self.setPath(path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def rebuild_path(self) -> None:
        self._build_painter_path()

    def setStraight(self, value: bool) -> None:
        self._straight = value
        self.rebuild_path()

    def addInflectionPoint(self) -> None:
        """Insert a midpoint between the last two existing points."""
        pts = self._all_points()
        if len(pts) < 2:
            raise ValueError("Not enough points to add an inflection point")
        mid = [
            (pts[-2][0] + pts[-1][0]) / 2,
            (pts[-2][1] + pts[-1][1]) / 2,
        ]
        self._inflection_points.append(mid)
        self._sync_handles()
        self.rebuild_path()

    def removeInflectionPoint(self) -> None:
        """Remove the last inflection point."""
        if not self._inflection_points:
            return
        self._inflection_points.pop()
        self._sync_handles()
        self.rebuild_path()
