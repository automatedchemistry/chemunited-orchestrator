from __future__ import annotations

import json
from math import ceil
from pathlib import Path
from typing import Iterable

from PyQt5.QtCore import QRectF, QSize, Qt
from PyQt5.QtGui import QBrush, QPainter
from PyQt5.QtSvg import QSvgGenerator
from PyQt5.QtWidgets import QGraphicsItem, QGraphicsScene

PLATFORM_SVG_RELATIVE_PATH = Path("draw") / "platform.svg"
PLATFORM_DEVICES_RELATIVE_PATH = Path("draw") / "platform-devices.json"

_EMPTY_SCENE_RECT = QRectF(0, 0, 640, 360)
_MARGIN = 24.0
_EXPORT_SCALE = 2.0


def export_platform_svg(
    scene: QGraphicsScene,
    path: Path,
    *,
    devices_path: Path | None = None,
    components: Iterable[tuple[str, object]] = (),
    scale: float = _EXPORT_SCALE,
) -> None:
    """Export the current platform scene as an SVG project companion file.

    If ``devices_path`` is given, a companion JSON manifest listing each
    component's bounding box in the *same pixel space as the exported SVG's
    viewBox* is written alongside it. The manifest is derived from the exact
    ``source_rect``/``size`` used for this render, inside the same
    hidden-handles/cleared-selection window — it must never be produced by a
    separate call, or its coordinates can drift out of sync with the SVG.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    scale = max(scale, 0.1)

    selected_items = tuple(scene.selectedItems())
    hidden_items = _visible_edit_handles(scene)
    previous_background = scene.backgroundBrush()

    try:
        scene.clearSelection()
        for item in hidden_items:
            item.setVisible(False)
        scene.setBackgroundBrush(QBrush(Qt.BrushStyle.NoBrush))

        source_rect = _export_rect(scene)
        size = QSize(
            max(1, ceil(source_rect.width() * scale)),
            max(1, ceil(source_rect.height() * scale)),
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
                Qt.IgnoreAspectRatio,  # type: ignore[attr-defined]
            )
        finally:
            painter.end()

        if devices_path is not None:
            _export_platform_devices(devices_path, components, source_rect, size)
    finally:
        scene.setBackgroundBrush(previous_background)
        for item in hidden_items:
            item.setVisible(True)
        for item in selected_items:
            item.setSelected(True)


def _export_platform_devices(
    devices_path: Path,
    components: Iterable[tuple[str, object]],
    source_rect: QRectF,
    size: QSize,
) -> None:
    scale_x = size.width() / source_rect.width()
    scale_y = size.height() / source_rect.height()

    devices: list[dict] = []
    for name, component in components:
        rect = component.graph.sceneBoundingRect()
        devices.append(
            {
                "id": name,
                "label": name,
                "figure": component.inf.figure,
                "is_electronic": component.inf.is_electronic,
                "x": (rect.x() - source_rect.x()) * scale_x,
                "y": (rect.y() - source_rect.y()) * scale_y,
                "w": rect.width() * scale_x,
                "h": rect.height() * scale_y,
            }
        )

    devices_path.parent.mkdir(parents=True, exist_ok=True)
    devices_path.write_text(
        json.dumps({"devices": devices}, indent=2), encoding="utf-8"
    )


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
