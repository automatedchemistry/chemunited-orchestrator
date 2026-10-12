"""Connections receive input near their route, without filling enclosed space."""

from math import hypot
from types import SimpleNamespace

import pytest
from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QContextMenuEvent
from qfluentwidgets import RoundMenu

from chemunited.draw.graph import DrawGraphicView
from chemunited.elements.component.component_factory import create_component
from chemunited.elements.component.component_parts.connection_point import (
    ConnectionPoint,
)
from chemunited.elements.connection.connection import (
    ElectricalConnectionItem,
    HeatConnectionItem,
    HydraulicConnectionItem,
    MovementConnectionItem,
)
from chemunited.shared.enums import SetupStepMode
from chemunited_core.connections import EdgeData, EdgeMode

CONNECTION_TYPES = (
    HydraulicConnectionItem,
    HeatConnectionItem,
    ElectricalConnectionItem,
    MovementConnectionItem,
)


@pytest.fixture
def make_connection(qapp):
    connections = []

    def make(
        item_type=HydraulicConnectionItem,
        *,
        origin=(0.0, 0.0),
        destination=(200.0, 100.0),
        inflections=((0.0, -100.0), (200.0, -100.0)),
        straight=True,
        name="D",
        ports=None,
    ):
        if ports is None:
            ports = (
                ConnectionPoint(origin, radius=2),
                ConnectionPoint(destination, radius=2),
            )
        data = EdgeData.from_mode(
            EdgeMode(
                origin="A",
                destination=name,
                classification=item_type.CATEGORY,
                inflection_points=list(inflections),
                straight_path=straight,
            )
        )
        connection = item_type(*ports, data)
        connections.append(connection)
        return connection

    yield make

    for connection in connections:
        connection.remove()


@pytest.fixture
def view(qtbot):
    graphic_view = DrawGraphicView()
    graphic_view.parent_ref = SimpleNamespace(
        orchestrator=SimpleNamespace(
            components={}, connections={}, show_connection_properties=lambda name: None
        )
    )
    graphic_view.scene().setSceneRect(QRectF(-60, -160, 340, 340))
    graphic_view.resize(700, 600)
    qtbot.addWidget(graphic_view)
    graphic_view.show()
    qtbot.waitExposed(graphic_view)
    return graphic_view


def _add_connection(view, connection):
    view.scene().addItem(connection)
    view.parent_ref.orchestrator.connections[connection.inf.name] = connection
    connection.set_frame_mode(SetupStepMode.PROTOCOLS)


def _route_normal(path, fraction):
    before = path.pointAtPercent(fraction - 0.001)
    after = path.pointAtPercent(fraction + 0.001)
    dx, dy = after.x() - before.x(), after.y() - before.y()
    length = hypot(dx, dy)
    return QPointF(-dy / length, dx / length)


@pytest.mark.parametrize("item_type", CONNECTION_TYPES)
@pytest.mark.parametrize("straight", [True, False], ids=["straight", "curved"])
def test_hit_shape_follows_route_and_excludes_enclosed_space(
    make_connection, item_type, straight
):
    connection = make_connection(item_type, straight=straight)
    path = connection.path()
    shape = connection.shape()
    enclosed = QPointF(60, 0)

    # The original open path implicitly fills this area when used for hit testing.
    assert path.contains(enclosed)
    assert not shape.contains(enclosed)
    for fraction in (0.15, 0.4, 0.7):
        center = path.pointAtPercent(fraction)
        normal = _route_normal(path, fraction)
        assert shape.contains(center)
        assert shape.contains(center + normal * 3.8)
        assert not shape.contains(center + normal * 4.2)

    assert connection.boundingRect().contains(shape.boundingRect())


@pytest.mark.parametrize("item_type", CONNECTION_TYPES)
def test_tolerance_is_continuous_at_dash_gaps_and_round_endpoints(
    make_connection, item_type
):
    connection = make_connection(item_type, destination=(120, 0), inflections=())
    shape = connection.shape()

    # For the dashed two-unit pen, x=10 falls in the first gap (8..12).
    assert shape.contains(QPointF(10, 0))
    assert shape.contains(QPointF(10, 3.9))
    assert not shape.contains(QPointF(10, 4.1))
    assert shape.contains(QPointF(-3.9, 0))
    assert not shape.contains(QPointF(-4.1, 0))
    assert shape.contains(QPointF(-2.7, -2.7))
    assert not shape.contains(QPointF(-3.5, -3.5))


def test_hit_tolerance_covers_a_pen_wider_than_eight_units(make_connection):
    connection = make_connection(destination=(120, 0), inflections=())
    connection.line_width = 12

    assert connection.shape().contains(QPointF(60, 5.9))
    assert not connection.shape().contains(QPointF(60, 6.1))
    assert connection.boundingRect().contains(connection.shape().boundingRect())


@pytest.mark.parametrize("straight", [True, False], ids=["straight", "curved"])
def test_enclosed_connection_receives_click_and_context_menu(
    qtbot, monkeypatch, view, make_connection, straight
):
    inner = make_connection(destination=(120, 0), inflections=(), name="G")
    outer = make_connection(straight=straight)
    _add_connection(view, inner)
    _add_connection(view, outer)
    outer.setZValue(inner.zValue() + 1)
    click_position = view.mapFromScene(QPointF(60, 0))

    assert view.itemAt(click_position) is inner
    qtbot.mouseClick(view.viewport(), Qt.LeftButton, pos=click_position)
    assert inner.isSelected()
    assert not outer.isSelected()

    menu_actions = []

    def choose_curved(menu, position):
        menu_actions.extend(action.text() for action in menu._actions)
        next(
            action for action in menu._actions if action.text() == "Switch to Curved"
        ).trigger()

    monkeypatch.setattr(RoundMenu, "exec_", choose_curved)
    event = QContextMenuEvent(
        QContextMenuEvent.Mouse,
        click_position,
        view.viewport().mapToGlobal(click_position),
    )
    view.contextMenuEvent(event)
    qtbot.waitUntil(lambda: not inner._straight)

    assert event.isAccepted()
    assert "Add Inflection Point" in menu_actions
    assert outer._straight is straight


def test_enclosed_empty_area_receives_background_interactions(
    qtbot, monkeypatch, view, make_connection
):
    connection = make_connection()
    _add_connection(view, connection)
    connection.setSelected(True)
    click_position = view.mapFromScene(QPointF(80, -50))

    assert connection.path().contains(QPointF(80, -50))
    assert view.itemAt(click_position) is None
    qtbot.mouseClick(view.viewport(), Qt.LeftButton, pos=click_position)
    assert not view.scene().selectedItems()

    menu_actions = []

    def choose_grid(menu, position):
        menu_actions.extend(action.text() for action in menu._actions)
        next(
            action for action in menu._actions if action.text() == "Show Grid"
        ).trigger()

    monkeypatch.setattr(RoundMenu, "exec_", choose_grid)
    event = QContextMenuEvent(
        QContextMenuEvent.Mouse,
        click_position,
        view.viewport().mapToGlobal(click_position),
    )
    view.contextMenuEvent(event)

    assert event.isAccepted()
    assert view.grid_enabled
    assert "Delete" not in menu_actions


@pytest.mark.parametrize("straight", [True, False], ids=["straight", "curved"])
def test_moving_bends_updates_scene_hits_and_bounds(view, make_connection, straight):
    connection = make_connection(straight=straight)
    _add_connection(view, connection)
    old_position = connection.path().pointAtPercent(0.5)
    assert connection in view.scene().items(old_position)
    old_bounds = connection.boundingRect()

    connection._handles[0].setPos(0, -220)
    connection._handles[1].setPos(200, -220)
    new_position = connection.path().pointAtPercent(0.5)
    near_new_position = new_position + _route_normal(connection.path(), 0.5) * 3.8

    assert connection not in view.scene().items(old_position)
    assert connection in view.scene().items(near_new_position)
    assert connection.boundingRect().top() < old_bounds.top()
    assert connection.boundingRect().contains(connection.shape().boundingRect())


@pytest.mark.parametrize("moving_endpoint", ["origin", "destination"])
def test_moving_component_updates_connection_hits_and_bounds(
    view, make_connection, moving_endpoint
):
    origin = create_component("HPLCPump", name="A", position=(0, 0))
    destination = create_component("HPLCPump", name="D", position=(300, 0))
    for component in (origin, destination):
        view.scene().addItem(component.graph)
    connection = make_connection(
        inflections=(),
        ports=(
            origin.graph.get_connection_point(2),
            destination.graph.get_connection_point(1),
        ),
    )
    _add_connection(view, connection)
    old_position = connection.path().pointAtPercent(0.5)
    old_bounds = connection.boundingRect()
    assert connection in view.scene().items(old_position)

    moving_component = origin if moving_endpoint == "origin" else destination
    moving_component.graph.moveBy(0, 160)
    new_position = connection.path().pointAtPercent(0.5)
    near_new_position = new_position + _route_normal(connection.path(), 0.5) * 3.8

    assert connection not in view.scene().items(old_position)
    assert connection in view.scene().items(near_new_position)
    assert connection.boundingRect() != old_bounds
    assert connection.boundingRect().contains(connection.shape().boundingRect())
