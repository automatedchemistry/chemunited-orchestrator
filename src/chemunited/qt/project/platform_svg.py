from __future__ import annotations

from math import ceil
from pathlib import Path

from PyQt5.QtCore import QRectF, QSize, Qt
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtSvg import QSvgGenerator
from PyQt5.QtWidgets import QGraphicsItem, QGraphicsScene

PLATFORM_SVG_RELATIVE_PATH = Path("draw") / "platform.svg"

_BACKGROUND = QColor("#ffffff")
_EMPTY_SCENE_RECT = QRectF(0, 0, 640, 360)
_MARGIN = 24.0


def export_platform_svg(scene: QGraphicsScene, path: Path) -> None:
    """Export the current platform scene as an SVG project companion file."""
    path.parent.mkdir(parents=True, exist_ok=True)

    selected_items = tuple(scene.selectedItems())
    hidden_items = _visible_edit_handles(scene)
    previous_background = scene.backgroundBrush()

    try:
        scene.clearSelection()
        for item in hidden_items:
            item.setVisible(False)
        scene.setBackgroundBrush(_BACKGROUND)

        source_rect = _export_rect(scene)
        size = QSize(
            max(1, ceil(source_rect.width())),
            max(1, ceil(source_rect.height())),
        )

        generator = QSvgGenerator()
        generator.setFileName(str(path))
        generator.setSize(size)
        generator.setViewBox(QRectF(0, 0, float(size.width()), float(size.height())))
        generator.setTitle("ChemUnited platform")
        generator.setDescription(
            "ChemUnited platform drawing exported from the project canvas."
        )

        painter = QPainter()
        if not painter.begin(generator):
            raise OSError(f"Could not create platform SVG export at '{path}'.")
        try:
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.TextAntialiasing, True)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            scene.render(
                painter,
                QRectF(0, 0, float(size.width()), float(size.height())),
                source_rect,
                Qt.IgnoreAspectRatio,
            )
        finally:
            painter.end()
    finally:
        scene.setBackgroundBrush(previous_background)
        for item in hidden_items:
            item.setVisible(True)
        for item in selected_items:
            item.setSelected(True)


def _visible_edit_handles(scene: QGraphicsScene) -> tuple[QGraphicsItem, ...]:
    handles: list[QGraphicsItem] = []
    for item in scene.items():
        for handle in getattr(item, "_handles", ()):
            if isinstance(handle, QGraphicsItem) and handle.isVisible():
                handles.append(handle)
    return tuple(handles)


def _export_rect(scene: QGraphicsScene) -> QRectF:
    if not any(item.isVisible() for item in scene.items()):
        return QRectF(_EMPTY_SCENE_RECT)

    rect = scene.itemsBoundingRect()
    if rect.isNull() or rect.width() <= 0 or rect.height() <= 0:
        return QRectF(_EMPTY_SCENE_RECT)
    return rect.adjusted(-_MARGIN, -_MARGIN, _MARGIN, _MARGIN)
