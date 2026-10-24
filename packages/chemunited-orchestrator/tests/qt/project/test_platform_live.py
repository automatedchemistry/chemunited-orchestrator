"""Tests for the live platform view's export (draw/platform-live.json).

What is tested:
- RotorChannel.paint, now drawn from chemunited-core's rotor_links, draws
  exactly the lines the previous implementation drew, for every rotary valve
  in every rotor position.
- The export leaves the live parts (rotor, status badges, relay lights) out of
  the SVG, restores them afterwards, and writes where they sit in the SVG's
  pixel space, plus a tight figure box per electronic device and the SVG hash.
"""

from __future__ import annotations

import hashlib
import json
from math import ceil

import numpy as np
import pytest
from PyQt5.QtCore import QPointF, QSize
from PyQt5.QtWidgets import QGraphicsScene

from chemunited.elements.component.component_factory import create_component
from chemunited.elements.component.glossary.valve.rotary_valve_graph import (
    RotaryValveGraph,
)
from chemunited.project.platform_svg import (
    _EXPORT_SCALE,
    _export_rect,
    export_platform_svg,
)
from chemunited_core.components.live_state import picture_kind
from chemunited_core.components.valve import rotate_rotor
from chemunited_core.figure_registry import COMPONENTS

ROTARY_VALVES = sorted(
    figure
    for figure, defn in COMPONENTS.items()
    if picture_kind(defn.data_class.from_mode(defn.mode_class(name="v"))) == "rotor"
)


class _RecordingPainter:
    def __init__(self) -> None:
        self.lines: set[frozenset[tuple[float, float]]] = set()

    def setPen(self, pen) -> None: ...

    def setBrush(self, brush) -> None: ...

    def drawLine(self, p1: QPointF, p2: QPointF) -> None:
        self.lines.add(_segment((p1.x(), p1.y()), (p2.x(), p2.y())))


def _segment(p1, p2) -> frozenset[tuple[float, float]]:
    return frozenset(
        (round(float(x), 6) + 0.0, round(float(y), 6) + 0.0) for x, y in (p1, p2)
    )


def _previous_paint(channel) -> set[frozenset[tuple[float, float]]]:
    """RotorChannel.paint as it was before it drew from rotor_links."""
    data, radius = channel._data, channel.radius
    lines = set()
    rotor_ports = [list(row) for row in data.rotor_ports]
    angles = np.arange(-np.pi / 2, 3 * np.pi / 2, 2 * np.pi / len(rotor_ports[0]))

    def at(i):
        return (radius * np.cos(angles[i]), radius * np.sin(angles[i]))

    if 0 in data.ports_by_number:
        for i, value in enumerate(data.rotor_ports[0]):
            if value == data.rotor_ports[1][0]:
                rotor_ports[0][i] = None
                lines.add(_segment((0.0, 0.0), at(i)))
    for i, value in enumerate(data.rotor_ports[0]):
        if value:
            for j, value_2 in enumerate(rotor_ports[0]):
                if value == value_2 and j != i:
                    lines.add(_segment(at(i), at(j)))
                    break
    return lines


@pytest.mark.parametrize("figure", ROTARY_VALVES)
def test_the_rotor_draws_what_it_drew_before_in_every_position(qtbot, figure):
    component = create_component(figure=figure, name="valve", position=(0.0, 0.0))
    channel = component.graph._internal_channel
    data = component.inf

    for _ in range(len(data.rotor_ports[0])):
        painter = _RecordingPainter()
        channel.paint(painter, None)
        assert painter.lines == _previous_paint(channel), data.rotor_ports
        assert painter.lines  # every position draws at least one channel
        data.rotor_ports = rotate_rotor(data.rotor_ports)


# ── export ───────────────────────────────────────────────────────────────────


@pytest.fixture
def platform(qtbot):
    scene = QGraphicsScene()
    specs = [
        ("Valve", "SixPortDistributionValve", (0.0, 0.0), {"angle": 90}),
        ("Injector", "SixPortTwoPositionValve", (260.0, 0.0), {"mirror": True}),
        ("Solenoid", "SolenoidValve", (0.0, 220.0), {}),
        ("Switch", "SolenoidValve2Way", (200.0, 220.0), {}),
        ("MFC", "MFCComponent", (400.0, 220.0), {}),
        ("Relay", "MultiChannelRelay", (600.0, 0.0), {"channels": 4}),
        ("Waste", "Sink", (600.0, 300.0), {}),
    ]
    components = []
    for name, figure, position, extra in specs:
        component = create_component(
            figure=figure, name=name, position=position, **extra
        )
        scene.addItem(component.graph)
        components.append((name, component))
    return scene, dict(components)


def _export(tmp_path, scene, components, prefix=""):
    svg_path = tmp_path / f"{prefix}platform.svg"
    live_path = tmp_path / f"{prefix}platform-live.json"
    export_platform_svg(
        scene, svg_path, live_path=live_path, components=components.items()
    )
    return svg_path, json.loads(live_path.read_text(encoding="utf-8"))


def _to_svg(scene):
    source_rect = _export_rect(scene)
    size = QSize(
        max(1, ceil(source_rect.width() * _EXPORT_SCALE)),
        max(1, ceil(source_rect.height() * _EXPORT_SCALE)),
    )
    sx = size.width() / source_rect.width()
    sy = size.height() / source_rect.height()

    def point(p: QPointF) -> list[float]:
        return [(p.x() - source_rect.x()) * sx, (p.y() - source_rect.y()) * sy]

    def box(rect) -> list[float]:
        return [*point(rect.topLeft()), rect.width() * sx, rect.height() * sy]

    return point, box, sx


def test_the_live_map_matches_the_svg_it_was_written_with(tmp_path, platform):
    scene, components = platform
    svg_path, live = _export(tmp_path, scene, components)

    assert live["svg_sha256"] == hashlib.sha256(svg_path.read_bytes()).hexdigest()
    assert live["displays"] == {}
    # Only electronic devices get commands, so only they have live parts.
    assert set(live["parts"]) == {
        "Valve",
        "Injector",
        "Solenoid",
        "Switch",
        "MFC",
        "Relay",
    }


def test_rotor_anchors_are_the_slot_points_in_svg_pixels(tmp_path, platform):
    scene, components = platform
    _, live = _export(tmp_path, scene, components)
    point, _, _ = _to_svg(scene)

    for name in ("Valve", "Injector"):  # one rotated, one mirrored
        channel = components[name].graph._internal_channel
        rotor = live["parts"][name]["rotor"]
        assert rotor["center"] == pytest.approx(
            point(channel.mapToScene(QPointF(0, 0))), abs=0.01
        )
        assert len(rotor["slots"]) == channel.slot_count
        for slot, anchor in enumerate(rotor["slots"], start=1):
            expected = point(channel.mapToScene(channel.slot_point(slot)))
            assert anchor == pytest.approx(expected, abs=0.01)

    # Slot 1 is the top one before the valve's own rotation: rotated by 90°,
    # it sits to the right of the centre.
    valve = live["parts"]["Valve"]["rotor"]
    assert valve["slots"][0][0] > valve["center"][0] + 1


def test_badge_and_light_anchors(tmp_path, platform):
    scene, components = platform
    _, live = _export(tmp_path, scene, components)
    point, box, sx = _to_svg(scene)

    for name in ("Solenoid", "Switch", "MFC"):
        overlay = components[name].graph._overlay
        assert live["parts"][name]["badge"]["box"] == pytest.approx(
            box(overlay.sceneBoundingRect()), abs=0.01
        )

    relay = components["Relay"].graph
    lights = live["parts"]["Relay"]["lights"]
    assert lights["r"] == pytest.approx(4 * sx, abs=0.01)
    assert lights["points"] == [
        pytest.approx(
            point(relay.bory.mapToScene(relay.bory.light_center(i))), abs=0.01
        )
        for i in range(4)
    ]


def test_figure_boxes_hold_the_figure_without_its_labels(tmp_path, platform):
    scene, components = platform
    _, live = _export(tmp_path, scene, components)
    _, box, _ = _to_svg(scene)

    for name, part in live["parts"].items():
        graph = components[name].graph
        figure = graph.figure_box()
        assert part["figure"] == pytest.approx(box(figure), abs=0.01)
        assert figure.contains(graph._svg.sceneBoundingRect())
        # Within the device's manifest box; 1 px of slack because a group's
        # rect isn't updated when a child moves after joining it (the relay's
        # figure does).
        assert graph.sceneBoundingRect().adjusted(-1, -1, 1, 1).contains(figure)
        if graph.rotation() == 0:
            # A rotated component's upright name can run across its figure.
            assert not figure.intersects(graph._name.sceneBoundingRect())

    relay = components["Relay"].graph
    assert relay.figure_box().contains(relay.bory.sceneBoundingRect())


def test_the_svg_leaves_out_the_live_state_and_restores_it(tmp_path, platform):
    scene, components = platform
    graphs = {name: component.graph for name, component in components.items()}
    live_items = [item for graph in graphs.values() for item in graph.live_items()]
    assert live_items and all(item.isVisible() for item in live_items)
    first, _ = _export(tmp_path, scene, components, "first-")

    # Change every live part: the drawing must not change with them.
    for name, command, kwargs in [
        ("Valve", "position", {"connect": "[[0, 4]]"}),
        ("Injector", "position", {"connect": "[[2, 3]]"}),
        ("Solenoid", "close", {}),
        ("Switch", "close", {}),
        ("MFC", "set-flow-rate", {"flowrate": "2 ml/min"}),
        ("Relay", "multiple_channel", {"values": "1111"}),
    ]:
        components[name].inf.apply(command, **kwargs)
        graphs[name].sync_visuals()
    second, _ = _export(tmp_path, scene, components, "second-")

    assert first.read_bytes() == second.read_bytes()
    assert all(item.isVisible() for item in live_items)


def test_without_a_live_path_nothing_else_is_written(tmp_path, platform):
    scene, components = platform
    export_platform_svg(scene, tmp_path / "platform.svg", components=components.items())
    assert sorted(p.name for p in tmp_path.iterdir()) == ["platform.svg"]


def test_valves_keep_their_rotor_in_the_scene(platform):
    _, components = platform
    for name in ("Valve", "Injector"):
        graph = components[name].graph
        assert isinstance(graph, RotaryValveGraph)
        assert graph.live_items() == (graph._internal_channel,)
