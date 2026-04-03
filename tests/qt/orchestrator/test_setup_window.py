"""Tests for SetupWindow — adding a component via the orchestrator.

What is tested:
- add_component registers the component in orchestrator.components
- add_component places the component's graph item in the scene
- duplicate name raises ValueError
"""

import pytest
from pytestqt.qtbot import QtBot

from chemunited.qt.setup import SetupWindow


class TestAddComponent:
    @pytest.fixture
    def window(self, qtbot: QtBot):
        w = SetupWindow()
        qtbot.addWidget(w)
        w.show()
        qtbot.waitExposed(w)
        return w

    def test_component_registered_in_orchestrator(
        self, window: SetupWindow, screenshot
    ):
        screenshot(window, "initial")

        window.orchestrator.add_component(
            name="HPLCPump",
            figure="HPLCPump",
            position=(0.0, 0.0),
        )

        screenshot(window, "after_add")

        assert "HPLCPump" in window.orchestrator.components

    def test_component_graph_item_in_scene(self, window: SetupWindow, screenshot):
        window.orchestrator.add_component(
            name="HPLCPump",
            figure="HPLCPump",
            position=(100.0, 100.0),
        )

        screenshot(window, "component_in_scene")

        component = window.orchestrator.components["HPLCPump"]
        scene_items = window.scene_attribute.items()
        assert component.graph in scene_items

    def test_duplicate_name_raises(self, window: SetupWindow):
        window.orchestrator.add_component(
            name="HPLCPump",
            figure="HPLCPump",
            position=(0.0, 0.0),
        )

        with pytest.raises(ValueError, match="already exists"):
            window.orchestrator.add_component(
                name="HPLCPump",
                figure="HPLCPump",
                position=(50.0, 50.0),
            )
