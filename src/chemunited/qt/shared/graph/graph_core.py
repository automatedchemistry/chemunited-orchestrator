from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QColor, QPainter, QPen
from PyQt5.QtWidgets import QGraphicsView
from qfluentwidgets import isDarkTheme

from chemunited.qt.shared.enums import SetupStepMode

from .scene_core import SceneCore

_ZOOM_FACTOR = 1.15  # scale multiplier per wheel step
_ZOOM_MIN = 0.05  # 5 % - maximum zoom out
_ZOOM_MAX = 10.0  # 1000 % - maximum zoom in


class GraphCore(QGraphicsView):
    MODE: SetupStepMode = SetupStepMode.DESIGN

    def __init__(self, scene: SceneCore | None = None, parent=None):
        super().__init__(parent)
        if scene is None:
            self.scene_attribute = SceneCore(self)
        else:
            self.scene_attribute = scene
        self.setScene(self.scene_attribute)

        # Zoom anchored to the position of the mouse cursor.
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)

        self._grid_enabled = False
        self._grid_step = 28
        self._grid_background_color: QColor | None = None
        self._grid_line_color: QColor | None = None

    # === Mouse Events ===
    def mousePressEvent(self, event):
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        super().mouseDoubleClickEvent(event)

    def wheelEvent(self, event):
        """Zoom only while Ctrl is pressed, otherwise keep default wheel behaviour."""
        if not event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            super().wheelEvent(event)
            return

        delta = event.angleDelta().y()
        if delta == 0:
            super().wheelEvent(event)
            return

        factor = _ZOOM_FACTOR if delta > 0 else 1.0 / _ZOOM_FACTOR

        # Clamp: read the current horizontal scale as the zoom proxy.
        current_scale = self.transform().m11()
        new_scale = current_scale * factor
        if new_scale < _ZOOM_MIN or new_scale > _ZOOM_MAX:
            return

        self.scale(factor, factor)
        event.accept()

    def contextMenuEvent(self, event):
        # Show custom right-click menus
        super().contextMenuEvent(event)

    # === Keyboard Events ===
    def keyPressEvent(self, event):
        # Handle key downs
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        # Handle key ups
        super().keyReleaseEvent(event)

    def build_grid(
        self,
        enabled: bool = True,
        *,
        step: int = 28,
        background_color: QColor | None = None,
        line_color: QColor | None = None,
    ) -> None:
        """Configure a simple grid rendered in the view background."""
        self._grid_enabled = enabled
        self._grid_step = max(4, step)
        self._grid_background_color = background_color
        self._grid_line_color = line_color
        self.update()

    def _default_grid_background_color(self) -> QColor:
        return QColor(39, 39, 39) if isDarkTheme() else QColor(249, 249, 249)

    def _default_grid_line_color(self) -> QColor:
        return QColor(255, 255, 255, 18) if isDarkTheme() else QColor(0, 0, 0, 16)

    def draw_grid_background(self, painter: QPainter, rect: QRectF) -> None:
        """Paint a reusable graph grid."""
        background = (
            self._grid_background_color or self._default_grid_background_color()
        )
        line_color = self._grid_line_color or self._default_grid_line_color()

        painter.fillRect(rect, background)
        painter.setPen(QPen(line_color, 1))

        step = self._grid_step
        left = int(rect.left()) - (int(rect.left()) % step)
        top = int(rect.top()) - (int(rect.top()) % step)

        x = left
        while x < rect.right():
            painter.drawLine(int(x), int(rect.top()), int(x), int(rect.bottom()))
            x += step

        y = top
        while y < rect.bottom():
            painter.drawLine(int(rect.left()), int(y), int(rect.right()), int(y))
            y += step

    # === Rendering ===
    def drawBackground(self, painter: QPainter | None, rect: QRectF) -> None:
        if painter is None:
            return

        if self._grid_enabled:
            self.draw_grid_background(painter, rect)
            return

        super().drawBackground(painter, rect)

    # === Utility ===
    def recenter_view(self):
        """Centralize the view according to the items currently present in the scene."""
        if self.scene():
            items_rect = self.scene().itemsBoundingRect()
            self.scene().setSceneRect(items_rect)
            self.fitInView(items_rect, Qt.KeepAspectRatio)
