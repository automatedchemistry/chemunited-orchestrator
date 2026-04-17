from PyQt5.QtGui import QColor
from pytestqt.qtbot import QtBot

from chemunited.qt.shared.graph import GraphCore, SceneCore


def test_grid_state_is_individual_for_each_graph_view(qtbot: QtBot):
    scene = SceneCore()
    first = GraphCore(scene)
    second = GraphCore(scene)
    qtbot.addWidget(first)
    qtbot.addWidget(second)

    first.set_grid_enabled(True)

    assert first.grid_enabled is True
    assert second.grid_enabled is False


def test_dark_background_state_is_shared_by_scene(qtbot: QtBot):
    scene = SceneCore()
    first = GraphCore(scene)
    second = GraphCore(scene)
    qtbot.addWidget(first)
    qtbot.addWidget(second)

    scene.set_dark_background_enabled(True)

    assert scene.dark_background_enabled is True
    assert scene.background_color() == QColor(30, 30, 30)
    assert scene.backgroundBrush().color() == QColor(30, 30, 30)
    assert first.scene_attribute is scene
    assert second.scene_attribute is scene
