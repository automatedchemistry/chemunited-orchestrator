"""Name and port-number labels must always render horizontal and unmirrored,
independent of the component's own angle/mirror state, so they stay readable
left-to-right on the canvas.
"""

import pytest
from PyQt5.QtCore import QPointF

from chemunited.elements.component.component_factory import create_component, list_components

ANGLES = [0, 45, 90, 135, 180, 225, 270, 315]
MIRRORS = [False, True]


def _pick_figure_with_ports() -> str:
    """Return a registered figure name that has at least one port."""
    categories, components = list_components()
    for names in categories.values():
        for name in names:
            manager = create_component(name, name="probe", position=(0, 0))
            if manager.graph._data.ports_by_number:
                return name
    pytest.fail("No registered component with at least one port was found")


@pytest.fixture(scope="module")
def figure_with_ports() -> str:
    return _pick_figure_with_ports()


def _is_upright_and_unmirrored(item) -> bool:
    """True if item's local +x axis maps to a purely horizontal, rightward
    vector in scene space -- i.e. no rotation (incl. 180deg) and no mirror.
    """
    origin = item.mapToScene(QPointF(0, 0))
    tip = item.mapToScene(QPointF(1, 0))
    dx = tip.x() - origin.x()
    dy = tip.y() - origin.y()
    return dx > 0 and abs(dy) < 1e-6


def _labels(graph):
    return [graph._name, *graph._port_labels.values()]


@pytest.mark.parametrize("angle", ANGLES)
@pytest.mark.parametrize("mirror", MIRRORS)
def test_labels_stay_upright_via_direct_rotation_and_mirror(
    qapp, figure_with_ports, angle, mirror
):
    manager = create_component(figure_with_ports, name="probe", position=(0, 0))
    graph = manager.graph

    graph.setRotation(angle)
    graph._apply_mirror(mirror)
    graph.post_layout()

    for label in _labels(graph):
        assert _is_upright_and_unmirrored(label)


@pytest.mark.parametrize("angle", ANGLES)
@pytest.mark.parametrize("mirror", MIRRORS)
def test_labels_stay_upright_via_sync(qapp, figure_with_ports, angle, mirror):
    manager = create_component(figure_with_ports, name="probe", position=(0, 0))
    graph = manager.graph

    updated_mode = graph.base_mode_instance.model_copy(
        update={"angle": angle, "mirror": mirror}
    )
    graph.sync(updated_mode)

    for label in _labels(graph):
        assert _is_upright_and_unmirrored(label)


def test_no_rotation_no_mirror_is_identity_transform(qapp, figure_with_ports):
    manager = create_component(figure_with_ports, name="probe", position=(0, 0))
    graph = manager.graph

    for label in _labels(graph):
        assert label.transform().isIdentity()


def test_post_layout_is_idempotent(qapp, figure_with_ports):
    manager = create_component(figure_with_ports, name="probe", position=(0, 0))
    graph = manager.graph

    graph.setRotation(123)
    graph._apply_mirror(True)
    graph.post_layout()
    transforms_before = [label.transform() for label in _labels(graph)]

    graph.post_layout()
    transforms_after = [label.transform() for label in _labels(graph)]

    assert transforms_before == transforms_after
