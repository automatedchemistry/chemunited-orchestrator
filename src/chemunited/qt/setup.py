from typing import override

from PyQt5.QtGui import QKeySequence
from qfluentwidgets import (
    Action,
    FluentIcon,
    NavigationItemPosition,
    RoundMenu,
)

from .draw.graph import DrawGraphicView
from .draw.tree_add import TreeAddItem
from .orchestrator import Orchestrator
from .protocols.graph import ProtocolGraphicView
from .protocols.process_list import ProtocolsWidget
from .protocols.workflows.workflow_widget import WorkflowsWidget
from .shared.editor.protocols.command_list import CommandList
from .shared.enums import WindowCategory
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
        self.drawFrame = FrameBase(parent=self)
        self.tree_add = TreeAddItem(self)

        # Protocol frame
        self.protocolFrame = FrameBase(parent=self)
        self.protocolGraph = ProtocolGraphicView(self.scene_attribute, self)
        self.workflows_protocol = WorkflowsWidget(self)
        self.command_list = CommandList(self)

        # Main Orchestrator Object
        # It depends on drawGraph being available during construction.
        self.orchestrator = Orchestrator(self)

        self.protocols_widget = ProtocolsWidget(self)

        self.buildUi()

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

        self.project_menu.addSeparator()

        self.save_project_action = Action(FluentIcon.SAVE, "Save Project", self)
        self.save_project_action.setShortcut(QKeySequence.Save)
        self.save_project_action.triggered.connect(self.save)
        self.project_menu.addAction(self.save_project_action)
        self.addAction(self.save_project_action)

    def _show_project_menu(self) -> None:
        self.refresh_recent_projects_menu()

        current_widget = self.stackWidget.currentWidget()
        if current_widget is not None:
            self.navigationInterface.setCurrentItem(current_widget.objectName())

        pos = self.project_menu_button.mapToGlobal(
            self.project_menu_button.rect().bottomRight()
        )
        self.project_menu.exec(pos)

    def refresh_recent_projects_menu(self) -> None:
        self.recent_projects_menu.clear()

        recent_projects = self.orchestrator.recent_projects.list()
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
            onClick=self.drawGraph.recenter_view,
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
            onClick=self.protocolGraph.recenter_view,
            position=NavigationItemPosition.TOP,
            tooltip="Recenter the view",
        )

        self.protocolFrame.addNavigationAction(
            icon=FluentIcon.SAVE,
            text="Save",
            onClick=self.save,
            position=NavigationItemPosition.TOP,
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

        self.SegmentWindow.addSubInterface(
            widget=self.protocolFrame,
            objectName="protocolFrame",
            text="Protocol",
            icon=FluentIcon.MOVIE,
        )

        self.addSubInterface(
            self.SegmentWindow,
            OrchestratorIcon.CHEMUNITED,
            "Segment",
        )
        self.switchTo(self.SegmentWindow)

    def save(self):
        self.orchestrator.save()

    def add_project(self):
        self.orchestrator.new_project()

    def load_project(self):
        self.orchestrator.load()

    def open_recent_project(self, path):
        self.orchestrator.open_recent_project(path)
