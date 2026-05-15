from loguru import logger

from .monitoring.graph import ExecutionGraph
from .monitoring.process_list import MonitorProcessesWidget
from .monitoring.status_animated import AnimatedOnlineIcon
from .orchestrator import Orchestrator
from .pre_run.summary_window import SummaryWindow
from .protocols.workflows.workflow_widget import WorkflowsWidget
from .shared.enums import SetupStepMode, WindowCategory
from .shared.graph import SceneCore
from .shared.icon import OrchestratorIcon
from .shared.widgets.frame_base import FrameBase
from .shared.widgets.main_window import MainWindowBase
from .shared.widgets.segment_widget import SegmentWindow


class MonitorWindow(MainWindowBase):
    TITLE = "ChemUnited Orchestrator"
    WINDOW_TYPE = WindowCategory.EXECUTION

    def __init__(self):
        super().__init__()

        self.scene_attribute = SceneCore()
        self.SegmentWindow = SegmentWindow(self)

        # Graph frame
        self.executionGraph = ExecutionGraph(self.scene_attribute, self)
        self.workflows_protocol = WorkflowsWidget(self, window=WindowCategory.EXECUTION)
        self.executionFrame = FrameBase(
            parent=self,
            classification=SetupStepMode.EXECUTION.name,
        )

        # Main Orchestrator Object
        self.orchestrator = Orchestrator(self)

        self.protocols_widget = MonitorProcessesWidget(self)

        self.summary_window = None

        self.buildUi()

    def buildUi(self):
        super().buildUi()

    def initNavigation(self):
        super().initNavigation()

        self.executionFrame.setGraphWidget(self.executionGraph)
        self.executionFrame.setWorkflowWidget(self.workflows_protocol)

        self.status_widget = self.executionFrame.addNavigationAction(
            icon=OrchestratorIcon.OFFLINE,
            text="Offline",
            tooltip="Connect components",
            onClick=self.switch_components_connection,
        )
        self.status_animation: AnimatedOnlineIcon | None = None

        self.executionFrame.addNavigationAction(
            icon=OrchestratorIcon.HOME,
            text="Home",
            onClick=self.recenter_views,
            tooltip="Recenter the view",
        )

        self.executionFrame.addSubInterface(
            widget=self.protocols_widget,
            text="Protocols",
            icon=OrchestratorIcon.PROCESS,
        )

        self.executionFrame.addNavigationAction(
            icon=OrchestratorIcon.JSON,
            text="Summary",
            onClick=self.show_summary,
            tooltip="Show parameters summary",
        )

        self.addSubInterface(
            self.executionFrame,
            text="Execution",
            icon=OrchestratorIcon.CHEMUNITED,
        )

    def switch_components_connection(self):
        is_connected = self.status_widget.text() == "Online"

        if is_connected:
            if self.status_animation is not None:
                self.status_animation.stop(reset_to_online=False)
            self.status_widget.setIcon(OrchestratorIcon.OFFLINE)
            self.status_widget.setText("Offline")
            self.status_widget.setToolTip("Connect components")
        else:
            if self.status_animation is None:
                self.status_animation = AnimatedOnlineIcon(self.status_widget, self)
            self.status_animation.start()
            self.status_widget.setText("Online")
            self.status_widget.setToolTip("Disconnect components")

    def recenter_views(self):
        self.executionGraph.recenter_view()
        self.workflows_protocol.recenter_view()

    def show_summary(self):
        if file := self.orchestrator.project_protocol_script_dir:
            if self.summary_window is None:
                self.summary_window = SummaryWindow.inspect_file(file_path=file)
            self.summary_window.show()
        else:
            logger.error("No project protocol script directory found.")
