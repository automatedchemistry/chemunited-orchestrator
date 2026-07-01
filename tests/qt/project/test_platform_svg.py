"""Tests for the platform SVG + device-manifest export.

What is tested:
- The device manifest's per-device bounding boxes are computed from the exact
  same `source_rect`/`size` pair used to render the SVG, so recomputing the
  transform independently (from each component's `sceneBoundingRect()`) must
  match the manifest's numbers.
- An empty scene still writes `{"devices": []}` rather than omitting the file.
"""

from __future__ import annotations

import json
import re
from math import ceil

import pytest
from PyQt5.QtCore import QSize
from PyQt5.QtWidgets import QGraphicsScene

from chemunited.elements.component.component_factory import (
    create_component,
    list_components,
)
from chemunited.project.platform_svg import (
    _EXPORT_SCALE,
    _export_rect,
    export_platform_svg,
)


def _two_figures() -> list[str]:
    _, components = list_components()
    figures = list(components.keys())
    assert len(figures) >= 2, "Expected at least two registered component figures"
    return figures[:2]


def test_platform_devices_manifest_matches_svg_viewbox(qtbot, tmp_path):
    scene = QGraphicsScene()
    figures = _two_figures()
    named_components = []
    for index, figure in enumerate(figures):
        name = f"{figure}-{index}"
        component = create_component(
            figure=figure,
            name=name,
            position=(index * 220.0, index * 90.0),
        )
        scene.addItem(component.graph)
        named_components.append((name, component))

    svg_path = tmp_path / "platform.svg"
    devices_path = tmp_path / "platform-devices.json"
    export_platform_svg(
        scene,
        svg_path,
        devices_path=devices_path,
        components=named_components,
    )

    svg_text = svg_path.read_text(encoding="utf-8")
    match = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg_text)
    assert match is not None, "Exported SVG is missing a viewBox"
    viewbox_width, viewbox_height = float(match.group(1)), float(match.group(2))

    manifest = json.loads(devices_path.read_text(encoding="utf-8"))
    devices = {device["id"]: device for device in manifest["devices"]}
    assert set(devices) == {name for name, _ in named_components}

    # Recompute the expected transform independently from the same scene state,
    # using the exact ceil()-rounded size (not the nominal scale), and assert
    # the manifest agrees with both the SVG's own viewBox and this transform.
    source_rect = _export_rect(scene)
    size = QSize(
        max(1, ceil(source_rect.width() * _EXPORT_SCALE)),
        max(1, ceil(source_rect.height() * _EXPORT_SCALE)),
    )
    assert size.width() == pytest.approx(viewbox_width)
    assert size.height() == pytest.approx(viewbox_height)

    scale_x = size.width() / source_rect.width()
    scale_y = size.height() / source_rect.height()

    for name, component in named_components:
        rect = component.graph.sceneBoundingRect()
        expected = {
            "x": (rect.x() - source_rect.x()) * scale_x,
            "y": (rect.y() - source_rect.y()) * scale_y,
            "w": rect.width() * scale_x,
            "h": rect.height() * scale_y,
        }
        device = devices[name]
        assert device["x"] == pytest.approx(expected["x"])
        assert device["y"] == pytest.approx(expected["y"])
        assert device["w"] == pytest.approx(expected["w"])
        assert device["h"] == pytest.approx(expected["h"])
        assert device["figure"] == component.inf.figure
        assert device["is_electronic"] == component.inf.is_electronic


def test_platform_devices_manifest_empty_scene_writes_empty_list(qtbot, tmp_path):
    scene = QGraphicsScene()
    svg_path = tmp_path / "platform.svg"
    devices_path = tmp_path / "platform-devices.json"

    export_platform_svg(scene, svg_path, devices_path=devices_path, components=())

    assert devices_path.is_file()
    manifest = json.loads(devices_path.read_text(encoding="utf-8"))
    assert manifest == {"devices": []}
