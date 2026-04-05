from typing import override

from qfluentwidgets import FluentIcon, NavigationItemPosition

from .draw.graph import DrawGraphicView
from .draw.tree_add import TreeAddItem
from .orchestrator import Orchestrator
from .protocols.graph import ProtocolGraphicView
from .protocols.process_list import ProtocolsWidget
from .protocols.workflows.workflow_widget import WorkflowsWidget
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

        # Main Orchestrator Object
        # It depends on drawGraph being available during construction.
        self.orchestrator = Orchestrator(self)

        self.protocols_widget = ProtocolsWidget(self)

        self.buildUi()

    @override
    def initNavigation(self):
        super().initNavigation()

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
