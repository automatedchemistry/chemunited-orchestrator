"""Offscreen contact-sheet renderer for component figures (test helper only).

Renders every registered component (or a selection) through the real
GraphComponent pipeline into a PNG, so figure artwork can be reviewed
without opening a window. Each component is drawn twice — on the light
and on the dark scene background — because both are used in the app.

Usage::

    python __render_components.py [OUT.png] [--only Name1,Name2] [--scale 2]
    python __render_components.py OUT.png --raw     # raw SVG files, no Qt items
    python __render_components.py OUT.png --fill 0.6  # preview vessels with liquid
    python __render_components.py OUT.png --figures DIR  # use the SVGs in DIR instead
    python __render_components.py --icons DIR  # write tree-palette icons (export_svg)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

if sys.platform != "win32":  # windows plugin renders fonts; no window is shown
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QByteArray, QRectF, Qt  # noqa: E402
from PyQt5.QtGui import QColor, QFont, QImage, QPainter, QPen  # noqa: E402
from PyQt5.QtSvg import QSvgRenderer  # noqa: E402
from PyQt5.QtWidgets import QApplication, QGraphicsScene  # noqa: E402

from chemunited.elements.component.component_factory import (  # noqa: E402
    list_components,
)
from chemunited.elements.component.glossary.vessels.common import (  # noqa: E402
    FlaskContent,
)
from chemunited.elements.component.graph_item import GraphComponent  # noqa: E402
from chemunited_core.figure_registry import (  # noqa: E402
    get_figure_path,
    list_figures,
    register_figure,
)

CELL = 240
CAPTION_H = 22
COLUMNS = 6
LIGHT_BG = QColor(249, 249, 249)
DARK_BG = QColor(30, 30, 30)
DEMO_LIQUID = QColor(245, 158, 11, 210)
DEMO_FILL = 0.0  # fraction of capacity shown as liquid (set by --fill)


def _build_component(figure: str, cls: type[GraphComponent]) -> GraphComponent:
    mode_payload = {
        "name": figure,
        "figure": figure,
        "position": (0, 0),
        "angle": 0,
        "heat_exchange": True,
    }
    mode = cls.BASEMODE.model_validate(mode_payload)
    component = cls(cls.METADATA.from_mode(mode))
    if DEMO_FILL > 0:
        _apply_demo_fill(component, DEMO_FILL)
    return component


def _apply_demo_fill(component: GraphComponent, fill: float) -> None:
    """Put a fake liquid level in every inventory so vessel artwork can be judged."""
    data = component.inf
    capacity = float(getattr(data, "capacity_value", 0.0) or 0.0)
    syringe_volume = getattr(data, "syringe_volume", None)
    if syringe_volume is not None:
        capacity = float(syringe_volume.to_base_units().magnitude)
    for inventory in getattr(data, "internal_inventories", {}).values():
        inventory.liq_content.volume = capacity * fill
    component.sync_visuals()


def _draw_caption(painter: QPainter, rect: QRectF, text: str, dark: bool) -> None:
    font = QFont("Segoe UI")
    font.setPixelSize(12)
    painter.setFont(font)
    painter.setPen(QColor(220, 220, 220) if dark else QColor(60, 60, 60))
    painter.drawText(rect, Qt.AlignCenter, text)  # type: ignore[attr-defined]


def _render_component_tile(
    figure: str, cls: type[GraphComponent], dark: bool, scale: float
) -> QImage:
    scene = QGraphicsScene()
    scene.setBackgroundBrush(DARK_BG if dark else LIGHT_BG)
    component = _build_component(figure, cls)
    scene.addItem(component)
    source = component.sceneBoundingRect().united(
        component.childrenBoundingRect().translated(component.pos())
    )
    source = source.adjusted(-8, -8, 8, 8)

    size = int(CELL * scale)
    image = QImage(size, size + int(CAPTION_H * scale), QImage.Format_ARGB32)
    image.fill(DARK_BG if dark else LIGHT_BG)
    painter = QPainter(image)
    painter.setRenderHints(
        QPainter.Antialiasing
        | QPainter.TextAntialiasing
        | QPainter.SmoothPixmapTransform
    )
    # keep 1 scene px == `scale` image px, unless the figure is too big
    fit = min(1.0, (CELL - 8) / max(source.width(), source.height()))
    w, h = source.width() * fit * scale, source.height() * fit * scale
    target = QRectF((size - w) / 2, (size - h) / 2, w, h)
    scene.render(painter, target, source, Qt.KeepAspectRatio)  # type: ignore[attr-defined]
    painter.resetTransform()
    _draw_caption(
        painter,
        QRectF(0, size, size, CAPTION_H * scale),
        f"{figure}" + ("" if fit == 1.0 else f"  ({fit:.0%})"),
        dark,
    )
    painter.end()
    scene.removeItem(component)
    return image


def _render_svg_tile(name: str, dark: bool, scale: float) -> QImage:
    size = int(CELL * scale)
    image = QImage(size, size + int(CAPTION_H * scale), QImage.Format_ARGB32)
    image.fill(DARK_BG if dark else LIGHT_BG)
    renderer = QSvgRenderer(QByteArray(get_figure_path(name).read_bytes()))
    vb = renderer.viewBoxF()
    pad = 16 * scale
    factor = min((size - 2 * pad) / vb.width(), (size - 2 * pad) / vb.height())
    w, h = vb.width() * factor, vb.height() * factor
    painter = QPainter(image)
    painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
    target = QRectF((size - w) / 2, (size - h) / 2, w, h)
    painter.setPen(QPen(QColor(128, 128, 128, 80), 1, Qt.DashLine))  # type: ignore[attr-defined]
    painter.drawRect(target)
    renderer.render(painter, target)
    _draw_caption(painter, QRectF(0, size, size, CAPTION_H * scale), name, dark)
    painter.end()
    return image


def _export_icons(out_dir: Path, only: set[str]) -> None:
    """Write <Name>.svg palette icons as each component looks when first dropped."""
    out_dir.mkdir(parents=True, exist_ok=True)
    categories, components = list_components()
    count = 0
    for figures in categories.values():
        for figure in figures:
            if only and figure not in only:
                continue
            cls = components[figure]
            mode = cls.BASEMODE.model_validate(
                {"name": figure, "figure": figure, "position": (0, 0), "angle": 0}
            )
            cls(cls.METADATA.from_mode(mode)).export_svg(out_dir / f"{figure}.svg")
            count += 1
    print(f"exported {count} icons to {out_dir}")


def _compose(tiles: list[tuple[QImage, QImage]], out: Path, columns: int) -> None:
    tile_w = tiles[0][0].width()
    tile_h = tiles[0][0].height()
    cols = min(columns, len(tiles))
    rows = (len(tiles) + cols - 1) // cols
    sheet = QImage(cols * tile_w * 2, rows * tile_h, QImage.Format_ARGB32)
    sheet.fill(QColor(200, 200, 200))
    painter = QPainter(sheet)
    for i, (light, dark) in enumerate(tiles):
        r, c = divmod(i, cols)
        painter.drawImage(c * tile_w * 2, r * tile_h, light)
        painter.drawImage(c * tile_w * 2 + tile_w, r * tile_h, dark)
    painter.setPen(QPen(QColor(150, 150, 150), 1))
    for c in range(1, cols):
        painter.drawLine(c * tile_w * 2, 0, c * tile_w * 2, sheet.height())
    for r in range(1, rows):
        painter.drawLine(0, r * tile_h, sheet.width(), r * tile_h)
    painter.end()
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(str(out))
    print(f"saved {out} ({sheet.width()}x{sheet.height()}, {len(tiles)} items)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("out", nargs="?", default="__components.png")
    parser.add_argument("--only", default="", help="comma-separated names")
    parser.add_argument("--raw", action="store_true", help="render raw SVG files")
    parser.add_argument("--scale", type=float, default=1.5)
    parser.add_argument("--cols", type=int, default=COLUMNS)
    parser.add_argument("--fill", type=float, default=0.0)
    parser.add_argument("--figures", default="", help="folder of override SVGs")
    parser.add_argument("--icons", default="", help="export palette icons to DIR")
    args = parser.parse_args()

    if args.figures:
        for svg in sorted(Path(args.figures).glob("*.svg")):
            register_figure(svg.stem, svg, override=True)

    if args.fill > 0:
        global DEMO_FILL
        DEMO_FILL = args.fill
        FlaskContent.content_color = lambda self, iventory=None: DEMO_LIQUID  # type: ignore[method-assign]

    only = {n for n in args.only.split(",") if n}

    _app = QApplication.instance() or QApplication(sys.argv)
    if args.icons:
        _export_icons(Path(args.icons), only)
        return

    tiles: list[tuple[QImage, QImage]] = []
    if args.raw:
        for name in list_figures():
            if only and name not in only:
                continue
            tiles.append(
                (
                    _render_svg_tile(name, False, args.scale),
                    _render_svg_tile(name, True, args.scale),
                )
            )
    else:
        categories, components = list_components()
        for figures in categories.values():
            for figure in figures:
                if only and figure not in only:
                    continue
                try:
                    tiles.append(
                        (
                            _render_component_tile(
                                figure, components[figure], False, args.scale
                            ),
                            _render_component_tile(
                                figure, components[figure], True, args.scale
                            ),
                        )
                    )
                except Exception as exc:  # keep going; report broken figures
                    print(f"!! {figure}: {type(exc).__name__}: {exc}")
    if tiles:
        _compose(tiles, Path(args.out), args.cols)


if __name__ == "__main__":
    main()
