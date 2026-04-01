from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPainter
from PyQt5.QtWidgets import (
    QGraphicsView,
)

from chemunited.qt.shared.enums import SetupStepMode

from .scene_core import SceneCore

_ZOOM_FACTOR   = 1.15   # scale multiplier per wheel step
_ZOOM_MIN      = 0.05   # 5 % — maximum zoom out
_ZOOM_MAX      = 10.0   # 1000 % — maximum zoom in


class GraphCore(QGraphicsView):
    MODE: SetupStepMode = SetupStepMode.DESIGN

    def __init__(self, scene: SceneCore | None = None, parent=None):
        super().__init__(parent)
        if scene is None:
            self.scene_attribute = SceneCore(self)
        else:
            self.scene_attribute = scene
        self.setScene(self.scene_attribute)

        # Zoom anchored to the position of the mouse cursor
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)

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
        """Zoom in/out with the mouse wheel.

        - Plain wheel  → zoom (scale anchored to cursor position).
        - Ctrl + wheel → same, kept for compatibility with trackpad pinch.
        Zoom level is clamped between _ZOOM_MIN and _ZOOM_MAX.
        """
        delta = event.angleDelta().y()
        if delta == 0:
            super().wheelEvent(event)
            return

        factor = _ZOOM_FACTOR if delta > 0 else 1.0 / _ZOOM_FACTOR

        # Clamp: read the current horizontal scale as the zoom proxy
        current_scale = self.transform().m11()
        new_scale = current_scale * factor
        if new_scale < _ZOOM_MIN or new_scale > _ZOOM_MAX:
            return

        self.scale(factor, factor)


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

    # === Rendering ===
    def drawBackground(self, painter: QPainter | None, rect) -> None:
        # Customize the background (e.g. to draw a grid lattice layout)
        if painter is None:
            return
        super().drawBackground(painter, rect)

    # === Utility ===
    def recenter_view(self):
        """
        Centralize the view according to the items currently present in the scene.
        """
        if self.scene():
            # Get the bounding box of all items
            items_rect = self.scene().itemsBoundingRect()

            # Optionally update the scene dimensions to match
            self.scene().setSceneRect(items_rect)

            # Fit the view to this rect, maintaining aspect ratio
            self.fitInView(items_rect, Qt.KeepAspectRatio)
