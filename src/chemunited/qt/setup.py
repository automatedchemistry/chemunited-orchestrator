from typing import override

from qfluentwidgets import FluentIcon, NavigationItemPosition

from .shared.enums import WindowCategory
from .shared.graph import GraphCore, SceneCore
from .shared.icon import OrchestratorIcon
from .shared.widgets.frame_base import FrameBase
from .shared.widgets.main_window import MainWindowBase
from .shared.widgets.segment_widget import SegmentWindow


class MainWindow(MainWindowBase):
    TITLE = "ChemUnited Orchestrator"
    WINDOW_TYPE = WindowCategory.SETUP

    def __init__(self):
        super().__init__()

        self.scene_attribute = SceneCore()
        self.SegmentWindow = SegmentWindow(self)

        # Draw frame
        self.drawGraph = GraphCore(self.scene_attribute, self)
        self.drawFrame = FrameBase(parent=self)

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

        self.drawFrame.addNavigationAction(
            icon=FluentIcon.SAVE,
            text="Save",
            onClick=self.save,
            position=NavigationItemPosition.TOP,
            tooltip="Save the graph",
        )

    def save(self):
        pass
