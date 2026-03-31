from __future__ import annotations
from PyQt5.QtSvg import QGraphicsSvgItem, QSvgRenderer
from PyQt5.QtWidgets import QGraphicsItem
from PyQt5.QtCore import QRectF
from .scene_item import PATTERN_DIMENSION


class SvgLayer(QGraphicsSvgItem):
    """
    Renders a single SVG figure inside a GraphComponent group.

    Responsibilities:
      - Load and display the SVG for this component figure
      - Scale to a consistent size derived from Config.PATTERN_DIMENSION
      - Centre on the local origin (0, 0) so port positions align correctly
      - Apply the component rotation angle

    Not responsible for:
      - Theme changes (SVG artwork is self-contained)
      - Interaction (not selectable, not movable independently)
      - Animation
    """

    def __init__(self, svg_path, angle=0, scale=PATTERN_DIMENSION, parent=None):
        super().__init__(svg_path, parent=parent)

        # Explicitly disable caching — ensures SVG re-renders at every zoom level
        # Never use DeviceCoordinateCache or ItemCoordinateCache here
        self.setCacheMode(QGraphicsItem.NoCache)

        self.setFlag(QGraphicsItem.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.ItemIsMovable, False)

        self._scale = scale
        self._apply_scale()
        self.setRotation(angle)

    # ── public API ────────────────────────────────────────────────

    def update_angle(self, angle: int) -> None:
        """Apply a new rotation angle. Called by GraphComponent.sync()."""
        self.setRotation(angle)

    def update_figure(self, svg_path: str) -> None:
        """Swap the SVG figure. Called by GraphComponent.sync()."""
        self._svg_path = svg_path
        self.setSharedRenderer(QSvgRenderer(svg_path))
        self._apply_scale()
        self._centre()

    # ── internal ──────────────────────────────────────────────────

    def _apply_scale(self) -> None:
        """
        Scale the SVG so its longest side equals self._scale,
        then centre it on the local origin.
        """
        native = self.boundingRect()
        if native.width() == 0 or native.height() == 0:
            return

        factor = self._scale / max(native.width(), native.height())
        self.setScale(factor)
        self._centre()

    def _centre(self) -> None:
        """
        Shift the item so its visual centre sits at (0, 0).
        QGraphicsSvgItem renders from its top-left corner by default.
        """
        br = self.boundingRect()
        self.setTransformOriginPoint(br.center())
        self.setPos(
            -br.width()  * self.scale() / 2,
            -br.height() * self.scale() / 2,
        )