"""Tests for SetupWindow — adding a component via the orchestrator.

What is tested:
- add_component registers the component in orchestrator.components
- add_component places the component's graph item in the scene
- duplicate name raises ValueError
"""

import zipfile

import pytest
from PyQt5.QtGui import QKeySequence
from pytestqt.qtbot import QtBot
from qfluentwidgets import NavigationTreeWidget

from chemunited.core.common.enums import ConnectionType
from chemunited.qt.project.recent import RecentProjectsStore
from chemunited.qt.project.session import ProjectSession
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

    def test_component_string_quantities_are_validated(self, window: SetupWindow):
        window.orchestrator.add_component(
            name="FlowReactor",
            figure="FlowReactor",
            position=(0.0, 0.0),
            length="100 mm",
            diameter="1 mm",
        )

        component = window.orchestrator.components["FlowReactor"]
        assert component.inf.length.to_base_units().magnitude == pytest.approx(0.1)
        assert component.inf.diameter.to_base_units().magnitude == pytest.approx(0.001)

    def test_gantry3d_component_restores_movement_ports(self, window: SetupWindow):
        window.orchestrator.add_component(
            name="gantry",
            figure="Gantry3D",
            position=(0.0, 0.0),
            connections_number=6,
        )

        component = window.orchestrator.components["gantry"]
        assert component.inf.figure == "Gantry3D"
        assert len(component.inf.ports_by_number) == 7

    def test_photoreactor_restores_flow_ports(self, window: SetupWindow):
        window.orchestrator.add_component(
            name="photo reactor",
            figure="PhotoReactor",
            position=(0.0, 0.0),
        )

        component = window.orchestrator.components["photo reactor"]
        assert component.inf.figure == "PhotoReactor"
        assert set(component.inf.ports_by_number) == {1, 2}
        assert component.inf.ports_by_number[1].category == ConnectionType.HYDRAULIC
        assert component.inf.ports_by_number[2].category == ConnectionType.HYDRAULIC

    def test_thermal_controls_restore_heat_ports(self, window: SetupWindow):
        window.orchestrator.add_component(
            name="peltier",
            figure="PeltierCoolerTemperatureControl",
            position=(0.0, 0.0),
        )
        window.orchestrator.add_component(
            name="chiller",
            figure="TemperatureControl",
            position=(100.0, 0.0),
        )

        peltier = window.orchestrator.components["peltier"]
        chiller = window.orchestrator.components["chiller"]
        assert set(peltier.inf.ports_by_number) == {1}
        assert peltier.inf.ports_by_number[1].category == ConnectionType.HEAT
        assert set(chiller.inf.ports_by_number) == {1}
        assert chiller.inf.ports_by_number[1].category == ConnectionType.HEAT

    def test_pressure_control_restores_pressure_port(self, window: SetupWindow):
        window.orchestrator.add_component(
            name="PressureControl",
            figure="PressureControl",
            position=(0.0, 0.0),
        )

        component = window.orchestrator.components["PressureControl"]
        assert set(component.inf.ports_by_number) == {1}
        assert component.inf.ports_by_number[1].category == ConnectionType.HYDRAULIC

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
        missing_path = tmp_path / "missing.chemunited"
        project_path.write_text("", encoding="utf-8")
        store.add(project_path)
        store.add(missing_path)
        window.orchestrator.recent_projects = store

        window.refresh_recent_projects_menu()

        recent_actions = window.recent_projects_menu.actions()
        assert len(recent_actions) == 1
        assert recent_actions[0].text() == "demo.chemunited"
        assert recent_actions[0].toolTip() == str(project_path.resolve())
        assert store.list() == [project_path.resolve()]

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

    def test_save_exports_platform_svg_into_project_archive(
        self, window: SetupWindow, tmp_path
    ):
        working_dir = tmp_path / "demo"
        session = ProjectSession()
        session.new(name="demo", location=tmp_path, init_git=False)
        window.orchestrator.working_dir = working_dir
        window.orchestrator._session = session

        window.orchestrator.add_component(
            name="PumpA",
            figure="HPLCPump",
            position=(0.0, 0.0),
        )

        window.orchestrator.save()

        svg_path = working_dir / "draw" / "platform.svg"
        assert svg_path.exists()
        assert "<svg" in svg_path.read_text(encoding="utf-8")
        assert window.orchestrator._session.source_file == tmp_path / "demo.chemunited"

        with zipfile.ZipFile(tmp_path / "demo.chemunited") as archive:
            assert "draw/platform.svg" in archive.namelist()

    def test_save_does_not_overwrite_existing_process_file(
        self, window: SetupWindow, tmp_path
    ):
        working_dir = tmp_path / "demo"
        session = ProjectSession()
        session.new(name="demo", location=tmp_path, init_git=False)
        existing_process = working_dir / "protocols" / "React.py"
        existing_process.parent.mkdir(parents=True, exist_ok=True)
        existing_content = "# keep existing process implementation\n"
        existing_process.write_text(existing_content, encoding="utf-8")
        window.orchestrator.working_dir = working_dir
        window.orchestrator._session = session
        window.orchestrator.add_process("React")

        window.orchestrator.save()

        assert existing_process.read_text(encoding="utf-8") == existing_content

    def test_rename_process_saves_project_when_original_file_is_missing(
        self, window: SetupWindow, tmp_path
    ):
        working_dir = tmp_path / "demo"
        session = ProjectSession()
        session.new(name="demo", location=tmp_path, init_git=False)
        window.orchestrator.working_dir = working_dir
        window.orchestrator._session = session
        window.orchestrator.add_process("React")

        window.orchestrator.rename_process("React", "ReactRenamed")

        renamed_process = working_dir / "protocols" / "ReactRenamed.py"
        assert renamed_process.exists()
        assert not (working_dir / "protocols" / "React.py").exists()
        assert session.source_file == tmp_path / "demo.chemunited"

    def test_rename_process_updates_existing_saved_process_file(
        self, window: SetupWindow, tmp_path
    ):
        working_dir = tmp_path / "demo"
        session = ProjectSession()
        session.new(name="demo", location=tmp_path, init_git=False)
        window.orchestrator.working_dir = working_dir
        window.orchestrator._session = session
        window.orchestrator.add_process("React")
        window.orchestrator.save()

        window.orchestrator.rename_process("React", "ReactRenamed")

        old_process = working_dir / "protocols" / "React.py"
        renamed_process = working_dir / "protocols" / "ReactRenamed.py"
        renamed_content = renamed_process.read_text(encoding="utf-8")

        assert not old_process.exists()
        assert renamed_process.exists()
        assert 'class ReactRenamedProcessConfig(BaseModel):' in renamed_content
        assert (
            "class ReactRenamedProcess(Process[ReactRenamedProcessConfig]):"
            in renamed_content
        )
        assert '__process_label__ = "ReactRenamed"' in renamed_content

    def test_remove_process_deletes_existing_saved_process_file(
        self, window: SetupWindow, tmp_path
    ):
        working_dir = tmp_path / "demo"
        session = ProjectSession()
        session.new(name="demo", location=tmp_path, init_git=False)
        window.orchestrator.working_dir = working_dir
        window.orchestrator._session = session
        window.orchestrator.add_process("React")
        window.orchestrator.save()

        window.orchestrator.remove_process("React")

        assert "React" not in window.orchestrator.protocols
        assert not (working_dir / "protocols" / "React.py").exists()
        assert session.list_processes() == []

    def test_remove_process_without_saved_file_does_not_create_files(
        self, window: SetupWindow, tmp_path
    ):
        working_dir = tmp_path / "demo"
        session = ProjectSession()
        session.new(name="demo", location=tmp_path, init_git=False)
        window.orchestrator.working_dir = working_dir
        window.orchestrator._session = session
        window.orchestrator.add_process("React")

        window.orchestrator.remove_process("React")

        assert "React" not in window.orchestrator.protocols
        assert not (working_dir / "protocols" / "React.py").exists()
        assert session.source_file is None

    def test_build_draw_data_persists_current_component_geometry(
        self, window: SetupWindow
    ):
        window.orchestrator.add_component(
            name="HPLCPump",
            figure="HPLCPump",
            position=(0.0, 0.0),
        )

        component = window.orchestrator.components["HPLCPump"]
        component.graph.setPos(123.5, 456.25)
        component.graph.setRotation(90)

        assert component.inf.position == (123.5, 456.25)
        assert component.inf.angle == 90

        draw_data = window.orchestrator._build_draw_data()
        saved_component = draw_data["components"][0]

        assert saved_component["position"] == [123.5, 456.25]
        assert saved_component["angle"] == 90
