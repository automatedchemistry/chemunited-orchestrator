"""Tests for SetupWindow — adding a component via the orchestrator.

What is tested:
- add_component registers the component in orchestrator.components
- add_component places the component's graph item in the scene
- duplicate name raises ValueError
"""

import pytest
from PyQt5.QtGui import QKeySequence
from pytestqt.qtbot import QtBot
from qfluentwidgets import NavigationTreeWidget

from chemunited.qt.project.recent import RecentProjectsStore
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

    def test_project_menu_shortcuts(self, window: SetupWindow):
        assert isinstance(window.project_menu_button, NavigationTreeWidget)
        assert (
            window.navigationInterface.widget("project_menu")
            is window.project_menu_button
        )
        assert window.load_project_action.shortcut() == QKeySequence("Ctrl+A")
        assert window.save_project_action.shortcut() == QKeySequence.Save

    def test_recent_projects_menu_lists_saved_paths(
        self, window: SetupWindow, tmp_path
    ):
        store = RecentProjectsStore(tmp_path / "recent_projects.json")
        project_path = tmp_path / "demo.chemunited"
        project_path.write_text("", encoding="utf-8")
        store.add(project_path)
        window.orchestrator.recent_projects = store

        window.refresh_recent_projects_menu()

        recent_actions = window.recent_projects_menu.actions()
        assert len(recent_actions) == 1
        assert recent_actions[0].text() == "demo.chemunited"
        assert recent_actions[0].toolTip() == str(project_path.resolve())

    def test_save_updates_existing_project_file(self, window: SetupWindow, tmp_path):
        class DummySession:
            def __init__(self, source_file):
                self.source_file = source_file
                self.export_destination = None

            def save_draw(self, draw_data):
                self.draw_data = draw_data

            def export_chemunited(self, destination=None):
                self.export_destination = destination
                return self.source_file

        source_file = tmp_path / "loaded.chemunited"
        session = DummySession(source_file)
        store = RecentProjectsStore(tmp_path / "recent_projects.json")
        window.orchestrator.working_dir = tmp_path / "loaded"
        window.orchestrator._session = session
        window.orchestrator.recent_projects = store

        window.orchestrator.save()

        assert session.draw_data == {"components": [], "connections": []}
        assert session.export_destination == source_file
        assert store.list() == [source_file.resolve()]
