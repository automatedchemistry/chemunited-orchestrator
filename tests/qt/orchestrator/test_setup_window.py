"""Tests for SetupWindow — adding a component via the orchestrator.

What is tested:
- add_component registers the component in orchestrator.components
- add_component places the component's graph item in the scene
- duplicate name raises ValueError
"""

import zipfile
from types import SimpleNamespace

import pytest
from chemunited_core.common.enums import ConnectionType
from PyQt5.QtGui import QKeySequence
from pytestqt.qtbot import QtBot
from qfluentwidgets import NavigationTreeWidget

from chemunited.qt.mcp import McpServiceResult
from chemunited.qt.project.recent import RecentProjectsStore
from chemunited.qt.project.session import ProjectSession
from chemunited.qt.setup import SetupWindow
from chemunited.qt.shared.enums import SetupStepMode


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
        assert window.refresh_project_action.text() == "Refresh Project"
        assert not window.refresh_project_action.isEnabled()
        assert window.mcp_project_action.text() == "Enable MCP"
        assert not window.mcp_project_action.isEnabled()
        assert window.save_project_action.shortcut() == QKeySequence.Save

    def test_setup_step_mode_accepts_enum_and_name_strings(self):
        assert (
            SetupWindow._setup_step_mode(SetupStepMode.DESIGN) == SetupStepMode.DESIGN
        )
        assert SetupWindow._setup_step_mode("PROTOCOLS") == SetupStepMode.PROTOCOLS
        assert SetupWindow._setup_step_mode("not-a-step") is None

    def test_mcp_project_action_is_disabled_without_project(self, window: SetupWindow):
        window.update_project_actions()

        assert not window.mcp_project_action.isEnabled()
        assert (
            window.mcp_project_action.toolTip()
            == "Load or create a project before enabling MCP."
        )

    def test_mcp_project_action_starts_and_stops_service(
        self, window: SetupWindow, tmp_path
    ):
        class DummyMcpService:
            def __init__(self):
                self.is_running = False
                self.url = None

            def start(self):
                self.is_running = True
                self.url = "http://127.0.0.1:8765/mcp"
                return McpServiceResult(True, "started", self.url)

            def stop(self):
                self.is_running = False
                return McpServiceResult(True, "stopped")

        window.orchestrator.working_dir = tmp_path
        window.mcp_service = DummyMcpService()

        window.update_project_actions()
        assert window.mcp_project_action.isEnabled()

        window.toggle_mcp_service()

        assert window.mcp_project_action.isChecked()
        assert window.mcp_project_action.text() == "Disable MCP"
        assert (
            window.mcp_project_action.toolTip()
            == "Project MCP: http://127.0.0.1:8765/mcp"
        )

        window.toggle_mcp_service()

        assert not window.mcp_project_action.isChecked()
        assert window.mcp_project_action.text() == "Enable MCP"

    def test_refresh_project_action_is_disabled_without_project(
        self, window: SetupWindow
    ):
        window.update_project_actions()

        assert not window.refresh_project_action.isEnabled()
        assert (
            window.refresh_project_action.toolTip()
            == "Load or create a project before refreshing."
        )

    def test_refresh_project_asks_before_reloading(
        self, window: SetupWindow, tmp_path, monkeypatch
    ):
        confirmed: list[bool] = []
        refreshed: list[bool] = []
        window.orchestrator.working_dir = tmp_path
        monkeypatch.setattr(
            window.orchestrator,
            "_confirm_refresh_project",
            lambda: confirmed.append(True) or False,
        )
        monkeypatch.setattr(
            window.orchestrator,
            "refresh_current_project",
            lambda: refreshed.append(True) or True,
        )

        window.refresh_project()

        assert confirmed == [True]
        assert refreshed == []

    def test_refresh_project_reloads_external_draw_changes(
        self, window: SetupWindow, tmp_path, monkeypatch, qtbot: QtBot
    ):
        session = ProjectSession()
        session.new(name="demo", location=tmp_path, init_git=False)
        session.save_draw(
            {
                "components": [
                    {
                        "name": "PumpA",
                        "figure": "HPLCPump",
                        "position": [0.0, 0.0],
                    }
                ],
                "connections": [],
            }
        )
        window.orchestrator.open_project(tmp_path / "demo")
        source_file = tmp_path / "demo.chemunited"
        window.orchestrator._session.source_file = source_file

        session.save_draw(
            {
                "components": [
                    {
                        "name": "PumpB",
                        "figure": "HPLCPump",
                        "position": [100.0, 0.0],
                    }
                ],
                "connections": [],
            }
        )
        monkeypatch.setattr(
            window.orchestrator,
            "_confirm_refresh_project",
            lambda: True,
        )

        window.refresh_project()
        qtbot.waitUntil(lambda: "PumpB" in window.orchestrator.components, timeout=1000)

        assert "PumpA" not in window.orchestrator.components
        assert "PumpB" in window.orchestrator.components
        assert window.orchestrator._session.source_file == source_file

    def test_failed_refresh_keeps_current_project(self, window: SetupWindow, tmp_path):
        session = ProjectSession()
        session.new(name="demo", location=tmp_path, init_git=False)
        session.save_draw(
            {
                "components": [
                    {
                        "name": "PumpA",
                        "figure": "HPLCPump",
                        "position": [0.0, 0.0],
                    }
                ],
                "connections": [],
            }
        )
        working_dir = tmp_path / "demo"
        window.orchestrator.open_project(working_dir)
        (working_dir / "draw" / "setup.py").write_text(
            "def build_draw(platform):\n    raise RuntimeError('boom')\n",
            encoding="utf-8",
        )

        assert window.orchestrator.refresh_current_project() is False
        assert "PumpA" in window.orchestrator.components

    def test_refresh_project_action_is_disabled_for_online_project_monitor(
        self, window: SetupWindow, tmp_path
    ):
        working_dir = tmp_path / "demo"
        window.orchestrator.working_dir = working_dir
        monitor = SimpleNamespace(
            orchestrator=SimpleNamespace(working_dir=working_dir),
            status_widget=SimpleNamespace(text=lambda: "Online"),
            api_process=object(),
        )
        window.preRunFrame.protocols_list_widget._monitor_windows.append(monitor)

        window.update_project_actions()

        assert not window.refresh_project_action.isEnabled()
        assert (
            window.refresh_project_action.toolTip()
            == "Disconnect the running project API before refreshing."
        )

    def test_mcp_refresh_reloads_without_confirmation(
        self, window: SetupWindow, tmp_path, monkeypatch
    ):
        session = ProjectSession()
        session.new(name="demo", location=tmp_path, init_git=False)
        session.save_draw(
            {
                "components": [
                    {
                        "name": "PumpA",
                        "figure": "HPLCPump",
                        "position": [0.0, 0.0],
                    }
                ],
                "connections": [],
            }
        )
        window.orchestrator.open_project(tmp_path / "demo")
        session.save_draw(
            {
                "components": [
                    {
                        "name": "PumpB",
                        "figure": "HPLCPump",
                        "position": [100.0, 0.0],
                    }
                ],
                "connections": [],
            }
        )
        monkeypatch.setattr(
            window.orchestrator,
            "_confirm_refresh_project",
            lambda: pytest.fail("MCP refresh must not show confirmation"),
        )

        result = window.mcp_service.refresh_project_from_mcp()

        assert result["ok"] is True
        assert "PumpA" not in window.orchestrator.components
        assert "PumpB" in window.orchestrator.components

    def test_mcp_exports_platform_svg(self, window: SetupWindow, tmp_path):
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

        result = window.mcp_service.export_platform_svg_from_mcp(scale=3.0)

        svg_path = working_dir / "draw" / "platform.svg"
        assert result == {
            "ok": True,
            "path": "draw/platform.svg",
            "bytes": svg_path.stat().st_size,
            "scale": 3.0,
            "message": "Platform SVG exported.",
        }
        assert "<svg" in svg_path.read_text(encoding="utf-8")

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
                self.manifest = None

            def save_draw(self, draw_data):
                self.draw_data = draw_data

            def sync_process(self, _process_name, _workflow):
                return True

            def save_main_parameters(self, _content):
                pass

            def load_connectivity(self):
                return {"server_url": "", "associations": []}

            def save_connectivity(self, _data):
                pass

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

    def test_save_preserves_existing_main_parameters_file(
        self, window: SetupWindow, tmp_path
    ):
        working_dir = tmp_path / "demo"
        session = ProjectSession()
        session.new(name="demo", location=tmp_path, init_git=False)
        main_parameters_path = working_dir / "protocols" / "main_parameters.py"
        main_parameters_path.parent.mkdir(parents=True, exist_ok=True)
        custom_content = (
            "from pydantic import BaseModel\n\n"
            "class MainParameter(BaseModel):\n"
            "    custom_value: str = 'keep-me'\n"
        )
        main_parameters_path.write_text(custom_content, encoding="utf-8")
        window.orchestrator.working_dir = working_dir
        window.orchestrator._session = session

        window.orchestrator.save()

        assert main_parameters_path.read_text(encoding="utf-8") == custom_content
        with zipfile.ZipFile(tmp_path / "demo.chemunited") as archive:
            assert "protocols/main_parameters.py" in archive.namelist()
            archived_content = archive.read("protocols/main_parameters.py").decode(
                "utf-8"
            )
            assert archived_content.replace("\r\n", "\n") == custom_content

    def test_save_creates_main_parameters_file_when_missing(
        self, window: SetupWindow, tmp_path
    ):
        working_dir = tmp_path / "demo"
        session = ProjectSession()
        session.new(name="demo", location=tmp_path, init_git=False)
        main_parameters_path = working_dir / "protocols" / "main_parameters.py"
        if main_parameters_path.exists():
            main_parameters_path.unlink()
        window.orchestrator.working_dir = working_dir
        window.orchestrator._session = session

        window.orchestrator.save()

        content = main_parameters_path.read_text(encoding="utf-8")
        assert "class MainParameter(BaseModel):" in content
        with zipfile.ZipFile(tmp_path / "demo.chemunited") as archive:
            assert "protocols/main_parameters.py" in archive.namelist()

    def test_save_syncs_existing_process_file_in_place(
        self, window: SetupWindow, tmp_path
    ):
        working_dir = tmp_path / "demo"
        session = ProjectSession()
        session.new(name="demo", location=tmp_path, init_git=False)
        existing_process = working_dir / "protocols" / "React.py"
        existing_process.parent.mkdir(parents=True, exist_ok=True)
        existing_process.write_text(
            """
from __future__ import annotations

import networkx as nx
from pydantic import BaseModel, ConfigDict

from chemunited_workflow import (
    NodeExecutionContext,
    Process,
    WorkflowEdgeSpec,
    WorkflowNodeSpec,
)


class ProcessConfig(BaseModel):
    model_config = ConfigDict(frozen=True)


class CustomProcess(Process[ProcessConfig]):
    \"\"\"User-defined workflow process.\"\"\"

    def build_workflow(self) -> nx.DiGraph:
        graph = nx.DiGraph()

        graph.add_node(
            "start",
            **WorkflowNodeSpec(
                node_id="start",
                method="start",
                position=(0.0, 0.0),
            ).model_dump(exclude_none=True),
        )

        graph.add_node(
            "legacy_node",
            **WorkflowNodeSpec(
                node_id="legacy_node",
                method="legacy_step",
                position=(100.0, 0.0),
            ).model_dump(exclude_none=True),
        )

        graph.add_node(
            "end",
            **WorkflowNodeSpec(
                node_id="end",
                method="finish",
                position=(200.0, 0.0),
            ).model_dump(exclude_none=True),
        )

        graph.add_edge(
            "start",
            "legacy_node",
            **WorkflowEdgeSpec(
                condition=True,
            ).model_dump(exclude_none=True),
        )

        graph.add_edge(
            "legacy_node",
            "end",
            **WorkflowEdgeSpec(
                condition=True,
            ).model_dump(exclude_none=True),
        )

        return graph

    def legacy_step(self, ctx: NodeExecutionContext) -> bool:
        ctx.runtime.status_message = "Legacy step"
        return True

    def _prepare_stock(self) -> str:
        return "helper"
""".strip()
            + "\n",
            encoding="utf-8",
        )
        window.orchestrator.working_dir = working_dir
        window.orchestrator._session = session
        window.orchestrator.add_process("React")
        workflow = window.orchestrator.protocols["React"]
        workflow.add_block(
            node_id="fresh_node",
            method="fresh_step",
            position=(100.0, 100.0),
        )
        workflow.add_connection("start", "fresh_node")
        workflow.add_connection("fresh_node", "end")

        window.orchestrator.save()

        updated = existing_process.read_text(encoding="utf-8")
        assert '"fresh_node"' in updated
        assert "def legacy_step(" not in updated
        assert "def fresh_step(self, ctx: NodeExecutionContext) -> bool:" in updated
        assert "def _prepare_stock(self) -> str:" in updated

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
        original_content = (working_dir / "protocols" / "React.py").read_text(
            encoding="utf-8"
        )

        window.orchestrator.rename_process("React", "ReactRenamed")

        old_process = working_dir / "protocols" / "React.py"
        renamed_process = working_dir / "protocols" / "ReactRenamed.py"
        renamed_content = renamed_process.read_text(encoding="utf-8")
        init_content = (working_dir / "protocols" / "__init__.py").read_text(
            encoding="utf-8"
        )

        assert not old_process.exists()
        assert renamed_process.exists()
        assert renamed_content == original_content
        assert "class ProcessConfig(BaseModel):" in renamed_content
        assert "class CustomProcess(Process[ProcessConfig]):" in renamed_content
        assert "ReactRenamedProcess" not in renamed_content
        assert "__process_label__" not in renamed_content
        assert "__process_description__" not in renamed_content
        assert (
            "from .ReactRenamed import CustomProcess as ReactRenamedProcess, "
            "ProcessConfig as ReactRenamedConfig"
        ) in init_content
        assert '    "ReactRenamed": ReactRenamedProcess,' in init_content
        assert '    "React": ReactProcess,' not in init_content

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

    def test_segment_window_switching_updates_component_and_connection_modes(
        self, window: SetupWindow, qtbot: QtBot
    ):
        window.orchestrator.add_component(
            name="PumpA",
            figure="HPLCPump",
            position=(0.0, 0.0),
        )
        window.orchestrator.add_component(
            name="PumpB",
            figure="HPLCPump",
            position=(200.0, 0.0),
        )
        window.orchestrator.add_connection(
            origin="PumpA",
            destiny="PumpB",
            origin_port=2,
            destiny_port=1,
        )

        component = window.orchestrator.components["PumpA"].graph
        connection = window.orchestrator.connections["PumpA_2_PumpB_1"]
        connection.addInflectionPoint()
        qtbot.wait(0)

        expected_port_visibility = {
            port_num: port.show_in_graph
            for port_num, port in window.orchestrator.components[
                "PumpA"
            ].inf.ports_by_number.items()
        }

        assert {
            port_num: point.isVisible() for port_num, point in component._points.items()
        } == expected_port_visibility
        assert {
            port_num: label.isVisible()
            for port_num, label in component._port_labels.items()
        } == expected_port_visibility
        assert all(handle.isVisible() for handle in connection._handles)

        window.SegmentWindow.switchTo(window.protocolFrame)
        qtbot.wait(0)

        assert {
            port_num: point.isVisible() for port_num, point in component._points.items()
        } == expected_port_visibility
        assert {
            port_num: label.isVisible()
            for port_num, label in component._port_labels.items()
        } == expected_port_visibility
        assert all(not handle.isVisible() for handle in connection._handles)

        window.SegmentWindow.switchTo(window.connectivityFrame)
        qtbot.wait(0)

        assert not any(point.isVisible() for point in component._points.values())
        assert not any(label.isVisible() for label in component._port_labels.values())
        assert all(not handle.isVisible() for handle in connection._handles)

        window.SegmentWindow.switchTo(window.drawFrame)
        qtbot.wait(0)

        assert {
            port_num: point.isVisible() for port_num, point in component._points.items()
        } == expected_port_visibility
        assert {
            port_num: label.isVisible()
            for port_num, label in component._port_labels.items()
        } == expected_port_visibility
        assert all(handle.isVisible() for handle in connection._handles)
