from __future__ import annotations

import hashlib
import json
from math import ceil
from pathlib import Path
from typing import Any, Iterable

from PyQt5.QtCore import QPointF, QRectF, QSize, Qt
from PyQt5.QtGui import QBrush, QPainter
from PyQt5.QtSvg import QSvgGenerator
from PyQt5.QtWidgets import QGraphicsItem, QGraphicsScene

PLATFORM_SVG_RELATIVE_PATH = Path("draw") / "platform.svg"
PLATFORM_DEVICES_RELATIVE_PATH = Path("draw") / "platform-devices.json"
PLATFORM_LIVE_RELATIVE_PATH = Path("draw") / "platform-live.json"
PROCESS_WORKFLOWS_DIR_RELATIVE_PATH = Path("draw") / "workflows"

_EMPTY_SCENE_RECT = QRectF(0, 0, 640, 360)
_MARGIN = 24.0
_EXPORT_SCALE = 2.0


def export_platform_svg(
    scene: QGraphicsScene,
    path: Path,
    *,
    devices_path: Path | None = None,
    live_path: Path | None = None,
    components: Iterable[tuple[str, object]] = (),
    displays: Iterable[QGraphicsItem] = (),
    scale: float = _EXPORT_SCALE,
) -> None:
    """Export the current platform scene as an SVG project companion file.

    If ``devices_path`` is given, a companion JSON manifest listing each
    component's bounding box in the *same pixel space as the exported SVG's
    viewBox* is written alongside it. The manifest is derived from the exact
    ``source_rect``/``size`` used for this render, inside the same
    hidden-handles/cleared-selection window — it must never be produced by a
    separate call, or its coordinates can drift out of sync with the SVG.

    The parts of ``components`` that show run-time state (valve rotors,
    status badges, relay lights) are left out of the SVG, so it never bakes in
    a stale state, and so are the LCD ``displays``. If ``live_path`` is given,
    a second manifest says where those parts and LCDs sit, for the dashboard's
    live view to redraw them (see ``_export_platform_live``).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    scale = max(scale, 0.1)
    components = tuple(components)
    displays = tuple(displays)

    selected_items = tuple(scene.selectedItems())
    hidden_items = (
        *_visible_edit_handles(scene),
        *_visible_live_items(components),
        *(item for item in displays if item.isVisible()),
    )
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
        if live_path is not None:
            _export_platform_live(
                live_path, path, components, displays, source_rect, size
            )
    finally:
        scene.setBackgroundBrush(previous_background)
        for item in hidden_items:
            item.setVisible(True)
        for item in selected_items:
            item.setSelected(True)


class _SvgPixels:
    """Maps scene coordinates to the exported SVG's pixels (its viewBox)."""

    def __init__(self, source_rect: QRectF, size: QSize) -> None:
        self._origin = source_rect.topLeft()
        self._sx = size.width() / source_rect.width()
        self._sy = size.height() / source_rect.height()

    def box(self, rect: QRectF) -> dict[str, float]:
        return {
            "x": (rect.x() - self._origin.x()) * self._sx,
            "y": (rect.y() - self._origin.y()) * self._sy,
            "w": rect.width() * self._sx,
            "h": rect.height() * self._sy,
        }

    def convert(self, value: Any, ndigits: int = 2) -> Any:
        """Points become ``[x, y]``, rects ``[x, y, w, h]``, floats lengths."""
        if isinstance(value, QPointF):
            return [
                round((value.x() - self._origin.x()) * self._sx, ndigits),
                round((value.y() - self._origin.y()) * self._sy, ndigits),
            ]
        if isinstance(value, QRectF):
            box = self.box(value)
            return [round(box[key], ndigits) for key in ("x", "y", "w", "h")]
        if isinstance(value, dict):
            return {key: self.convert(item, ndigits) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [self.convert(item, ndigits) for item in value]
        if isinstance(value, float):
            return round(value * self._sx, ndigits)
        return value


def _export_platform_devices(
    devices_path: Path,
    components: Iterable[tuple[str, object]],
    source_rect: QRectF,
    size: QSize,
) -> None:
    pixels = _SvgPixels(source_rect, size)

    devices: list[dict] = []
    for name, component in components:
        rect = component.graph.sceneBoundingRect()  # type: ignore
        devices.append(
            {
                "id": name,
                "label": name,
                "figure": component.inf.figure,  # type: ignore
                "is_electronic": component.inf.is_electronic,  # type: ignore
                **pixels.box(rect),
            }
        )

    devices_path.parent.mkdir(parents=True, exist_ok=True)
    devices_path.write_text(
        json.dumps({"devices": devices}, indent=2), encoding="utf-8"
    )


def _export_platform_live(
    live_path: Path,
    svg_path: Path,
    components: Iterable[tuple[str, object]],
    displays: Iterable[QGraphicsItem],
    source_rect: QRectF,
    size: QSize,
) -> None:
    """Write where each device's live parts sit, in the SVG's pixels.

    ``parts`` maps each electronic component to ``figure``, a tight
    ``[x, y, w, h]`` box around its drawn figure (for running rings and
    command text), plus the geometry of each part the SVG leaves out, from
    ``GraphComponent.live_anchors()``: ``rotor`` (``center``, and ``slots``
    from slot 1), ``badge`` (``box``) or ``lights`` (``points`` and ``r``).
    ``displays`` maps each LCD's name to its ``box`` and the variable it
    shows: ``component``, ``command`` and ``kwargs``. ``svg_sha256`` is the
    hash of the SVG written alongside, so a map that no longer matches the
    SVG can be told apart.
    """
    pixels = _SvgPixels(source_rect, size)
    parts: dict[str, dict[str, Any]] = {}
    for name, component in components:
        if not component.inf.is_electronic:  # type: ignore[attr-defined]
            continue
        graph = component.graph  # type: ignore[attr-defined]
        parts[name] = {
            "figure": pixels.convert(graph.figure_box()),
            **pixels.convert(graph.live_anchors()),
        }

    live_path.parent.mkdir(parents=True, exist_ok=True)
    live_path.write_text(
        json.dumps(
            {
                "svg_sha256": hashlib.sha256(svg_path.read_bytes()).hexdigest(),
                "parts": parts,
                "displays": {
                    item.display.name: {  # type: ignore[attr-defined]
                        "box": pixels.convert(item.sceneBoundingRect()),
                        "component": item.display.component,  # type: ignore[attr-defined]
                        "command": item.display.command,  # type: ignore[attr-defined]
                        "kwargs": item.display.kwargs,  # type: ignore[attr-defined]
                    }
                    for item in displays
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _visible_live_items(
    components: Iterable[tuple[str, object]],
) -> tuple[QGraphicsItem, ...]:
    return tuple(
        item
        for _, component in components
        for item in component.graph.live_items()  # type: ignore[attr-defined]
        if item.isVisible()
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
