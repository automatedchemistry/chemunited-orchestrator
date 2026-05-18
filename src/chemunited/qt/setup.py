from pathlib import Path
from typing import override

from PyQt5.QtCore import pyqtSlot
from PyQt5.QtGui import QKeySequence
from qfluentwidgets import (
    Action,
    FluentIcon,
    NavigationItemPosition,
    RoundMenu,
)

from .connectivity.graph import ConnectivityGraphicView
from .connectivity.online_list import OnlineComponent
from .draw.graph import DrawGraphicView
from .draw.tree_add import TreeAddItem
from .mcp import ProjectMcpService
from .orchestrator import Orchestrator
from .pre_run.pre_run_frame import PreRunFrame
from .protocols.graph import ProtocolGraphicView
from .protocols.process_list import ProtocolsWidget
from .protocols.workflows.workflow_widget import WorkflowsWidget
from .shared.editor.parameters.main import MainParametersEditor
from .shared.editor.protocols.command_list import CommandList
from .shared.enums import SetupStepMode, WindowCategory
from .shared.graph import SceneCore
from .shared.icon import OrchestratorIcon
from .shared.widgets.frame_base import FrameBase
from .shared.widgets.main_window import MainWindowBase
from .shared.widgets.segment_widget import SegmentWindow


class SetupWindow(MainWindowBase):
    TITLE = "ChemUnited Orchestrator"
    WINDOW_TYPE = WindowCategory.SETUP

    def __init__(self):
        super().__init__()

        self.scene_attribute = SceneCore()
        self.SegmentWindow = SegmentWindow(self)

        # Draw frame
        self.drawGraph = DrawGraphicView(self.scene_attribute, self)
        self.drawFrame = FrameBase(
            parent=self,
            classification=SetupStepMode.DESIGN.name,
        )
        self.tree_add = TreeAddItem(self)

        # Protocol frame
        self.protocolFrame = FrameBase(
            parent=self,
            classification=SetupStepMode.PROTOCOLS.name,
        )
        self.protocolGraph = ProtocolGraphicView(self.scene_attribute, self)
        self.workflows_protocol = WorkflowsWidget(self)
        self.command_list = CommandList(self)
        self.parameter_list_widget: MainParametersEditor | None = None

        # Connectivity frame
        self.connectivityFrame = FrameBase(
            parent=self,
            classification=SetupStepMode.CONNECTIVITY.name,
        )
        self.connectivityGraph = ConnectivityGraphicView(self.scene_attribute, self)
        self.online_list = OnlineComponent(self)

        # Main Orchestrator Object
        # It depends on drawGraph being available during construction.
        self.orchestrator = Orchestrator(self)
        self.mcp_service = ProjectMcpService(self)

        self.preRunFrame = PreRunFrame(self)  # Pre-run frame

        self.protocols_widget = ProtocolsWidget(self)

        self.buildUi()

        # Signal connections
        self.SegmentWindow.current_widget_changed.connect(  # type: ignore[attr-defined]
            self._on_current_widget_changed
        )

    def initProjectMenu(self) -> None:
        self.project_menu = RoundMenu(parent=self)
        self.project_menu_button = self.navigationInterface.addItem(
            routeKey="project_menu",
            icon=FluentIcon.FOLDER,
            text="Project",
            onClick=self._show_project_menu,
            selectable=True,
            position=NavigationItemPosition.TOP,
            tooltip="Project",
        )

        self.add_project_action = Action(
            OrchestratorIcon.ADD_FOLDER,
            "Add Project...",
            self,
        )
        self.add_project_action.triggered.connect(self.add_project)
        self.project_menu.addAction(self.add_project_action)

        self.load_project_action = Action(
            OrchestratorIcon.OPEN_FOLDER,
            "Load Project...",
            self,
        )
        self.load_project_action.setShortcut(QKeySequence("Ctrl+A"))
        self.load_project_action.triggered.connect(self.load_project)
        self.project_menu.addAction(self.load_project_action)
        self.addAction(self.load_project_action)

        self.recent_projects_menu = RoundMenu("Recent Files", self.project_menu)
        self.project_menu.addMenu(self.recent_projects_menu)
        self.refresh_recent_projects_menu()

        self.project_menu.addSeparator()

        self.refresh_project_action = Action(
            OrchestratorIcon.UPDATE,
            "Refresh Project",
            self,
        )
        self.refresh_project_action.triggered.connect(self.refresh_project)
        self.project_menu.addAction(self.refresh_project_action)

        self.mcp_project_action = Action(
            OrchestratorIcon.LINK,
            "Enable MCP",
            self,
        )
        self.mcp_project_action.setCheckable(True)
        self.mcp_project_action.triggered.connect(self.toggle_mcp_service)
        self.project_menu.addAction(self.mcp_project_action)

        self.save_project_action = Action(FluentIcon.SAVE, "Save Project", self)
        self.save_project_action.setShortcut(QKeySequence.Save)
        self.save_project_action.triggered.connect(self.save)
        self.project_menu.addAction(self.save_project_action)
        self.addAction(self.save_project_action)
        self.update_project_actions()

    def _show_project_menu(self) -> None:
        self.refresh_recent_projects_menu()
        self.update_project_actions()

        current_widget = self.stackWidget.currentWidget()
        if current_widget is not None:
            self.navigationInterface.setCurrentItem(current_widget.objectName())

        pos = self.project_menu_button.mapToGlobal(
            self.project_menu_button.rect().bottomRight()
        )
        self.project_menu.exec(pos)

    def refresh_recent_projects_menu(self) -> None:
        self.recent_projects_menu.clear()

        recent_projects = self.orchestrator.recent_projects.prune_missing()
        if not recent_projects:
            empty_action = Action(FluentIcon.INFO, "No Recent Files", self)
            empty_action.setEnabled(False)
            self.recent_projects_menu.addAction(empty_action)
            return

        for project_path in recent_projects:
            action = Action(FluentIcon.DOCUMENT, project_path.name, self)
            action.setToolTip(str(project_path))
            action.triggered.connect(
                lambda checked=False, path=project_path: self.open_recent_project(path)
            )
            self.recent_projects_menu.addAction(action)

    @override
    def initNavigation(self):
        super().initNavigation()
        self.initProjectMenu()

        self.drawFrame.setGraphWidget(self.drawGraph)

        self.drawFrame.addNavigationAction(
            icon=OrchestratorIcon.HOME,
            text="Home",
            onClick=self.recenter_views,
            position=NavigationItemPosition.TOP,
            tooltip="Recenter the view",
        )

        self.drawFrame.addSubInterface(
            self.tree_add,
            FluentIcon.ADD,
            "Add",
            NavigationItemPosition.TOP,
        )

        self.drawFrame.addNavigationAction(
            icon=FluentIcon.SAVE,
            text="Save",
            onClick=self.save,
            position=NavigationItemPosition.BOTTOM,
            tooltip="Save the graph",
        )

        self.SegmentWindow.addSubInterface(
            widget=self.drawFrame,
            objectName="drawFrame",
            text="Draw",
            icon=FluentIcon.EDIT,
        )

        self.protocolFrame.setGraphWidget(self.protocolGraph)

        self.protocolFrame.setWorkflowWidget(self.workflows_protocol)

        self.protocolFrame.addNavigationAction(
            icon=OrchestratorIcon.HOME,
            text="Home",
            onClick=self.recenter_views,
            position=NavigationItemPosition.TOP,
            tooltip="Recenter the view",
        )

        self.protocolFrame.addNavigationAction(
            icon=FluentIcon.SAVE,
            text="Save",
            onClick=self.save,
            position=NavigationItemPosition.BOTTOM,
            tooltip="Save the graph",
        )

        self.protocolFrame.addSubInterface(
            widget=self.protocols_widget,
            text="Process List",
            icon=OrchestratorIcon.PROCESS,
            routeKey="protocols_widget",
        )

        self.protocolFrame.addSubInterface(
            widget=self.command_list,
            text="Command List",
            icon=OrchestratorIcon.BUILD,
            routeKey="command_list",
            onClick=self.command_list.sync_protocols,
        )

        self.protocolFrame.addNavigationAction(
            icon=OrchestratorIcon.VARIABLE,
            text="Main Parameters",
            position=NavigationItemPosition.TOP,
            onClick=self.open_main_parameters_editor,
            tooltip="Open the main parameters editor",
        )

        self.SegmentWindow.addSubInterface(
            widget=self.protocolFrame,
            objectName="protocolFrame",
            text="Protocol",
            icon=FluentIcon.MOVIE,
        )

        self.connectivityFrame.setGraphWidget(self.connectivityGraph)

        self.connectivityFrame.addSubInterface(
            widget=self.online_list,
            routeKey="online_list",
            text="Online List",
            icon=OrchestratorIcon.WIFI,
        )

        self.connectivityFrame.addNavigationAction(
            icon=OrchestratorIcon.HOME,
            text="Home",
            onClick=self.recenter_views,
            position=NavigationItemPosition.TOP,
            tooltip="Recenter the view",
        )

        self.connectivityFrame.addNavigationAction(
            icon=FluentIcon.SAVE,
            text="Save",
            onClick=self.save,
            position=NavigationItemPosition.BOTTOM,
            tooltip="Save the graph",
        )

        self.SegmentWindow.addSubInterface(
            widget=self.connectivityFrame,
            objectName="connectivityFrame",
            text="Connectivity",
            icon=FluentIcon.CONNECT,
        )

        self.SegmentWindow.addSubInterface(
            widget=self.preRunFrame,
            objectName="preRunFrame",
            text="Pre-run",
            icon=FluentIcon.ACCEPT_MEDIUM,
        )

        self.addSubInterface(
            self.SegmentWindow,
            OrchestratorIcon.CHEMUNITED,
            "Segment",
        )
        self.switchTo(self.SegmentWindow)

    _SAVE_COMMENTS = {
        SetupStepMode.DESIGN: "Save: design updated",
        SetupStepMode.PROTOCOLS: "Save: protocols updated",
        SetupStepMode.CONNECTIVITY: "Save: connectivity updated",
    }

    def save(self) -> None:
        current_widget = self.SegmentWindow.stackedWidget.currentWidget()
        classification = getattr(current_widget, "classification", SetupStepMode.DESIGN)
        comment = self._SAVE_COMMENTS.get(classification, "Save: project updated")
        self.orchestrator.save(comment)
        self.update_project_actions()

    def add_project(self):
        self.orchestrator.new_project()
        self.update_project_actions()

    def load_project(self):
        self.orchestrator.load()
        self.update_project_actions()

    def open_recent_project(self, path):
        self.orchestrator.open_recent_project(path)
        self.update_project_actions()

    def refresh_project(self) -> None:
        self.update_project_actions()
        if self.orchestrator.refresh_project():
            self.refresh_project_action.setEnabled(False)

    def update_project_actions(self) -> None:
        if not hasattr(self, "refresh_project_action"):
            return
        block_reason = self.orchestrator.refresh_project_block_reason()
        self.refresh_project_action.setEnabled(block_reason is None)
        self.refresh_project_action.setToolTip(
            block_reason or "Reload the current project from disk"
        )
        self._update_mcp_action()

    def toggle_mcp_service(self) -> None:
        if self.mcp_service.is_running:
            result = self.mcp_service.stop()
        else:
            result = self.mcp_service.start()
        self.update_project_actions()
        if not result.ok:
            self.FrameLoggings.detail_loggins.append(result.message)

    def _update_mcp_action(self) -> None:
        if not hasattr(self, "mcp_project_action"):
            return
        running = self.mcp_service.is_running
        can_start = self.orchestrator.working_dir is not None
        self.mcp_project_action.setEnabled(running or can_start)
        self.mcp_project_action.setChecked(running)
        self.mcp_project_action.setText("Disable MCP" if running else "Enable MCP")
        if running and self.mcp_service.url:
            self.mcp_project_action.setToolTip(f"Project MCP: {self.mcp_service.url}")
        elif can_start:
            self.mcp_project_action.setToolTip("Expose project files over local MCP")
        else:
            self.mcp_project_action.setToolTip(
                "Load or create a project before enabling MCP."
            )

    def open_main_parameters_editor(self):
        if self.orchestrator.working_dir is None:
            return

        if self.parameter_list_widget is None:
            self.parameter_list_widget = MainParametersEditor(
                path=Path(
                    self.orchestrator.working_dir / "protocols" / "main_parameters.py"
                ),
                class_name="MainParameter",
                parent=self,
            )
        self.parameter_list_widget.show()
        self.parameter_list_widget.raise_()
        self.parameter_list_widget.activateWindow()

    def close_main_parameters_editor(self) -> None:
        if self.parameter_list_widget is None:
            return
        self.parameter_list_widget.close()
        self.parameter_list_widget = None

    def recenter_views(self):
        self.drawGraph.recenter_view()
        self.protocolGraph.recenter_view()
        self.workflows_protocol.recenter_view()

    def closeEvent(self, event):
        if self.mcp_service.is_running:
            self.mcp_service.stop()
        super().closeEvent(event)

    @pyqtSlot(str)
    def _on_current_widget_changed(self, _route_key: str) -> None:
        current_widget = self.SegmentWindow.stackedWidget.currentWidget()
        classification = getattr(current_widget, "classification", None)
        if isinstance(classification, SetupStepMode):
            self.orchestrator.switch_to_step(classification)
