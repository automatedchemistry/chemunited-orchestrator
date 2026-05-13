from .monitoring.graph import ExecutionGraph
from .monitoring.process_list import MonitorProcessesWidget
from .orchestrator import Orchestrator
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

        self.buildUi()

    def buildUi(self):
        super().buildUi()

    def initNavigation(self):
        super().initNavigation()

        self.executionFrame.setGraphWidget(self.executionGraph)
        self.executionFrame.setWorkflowWidget(self.workflows_protocol)

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

        self.addSubInterface(
            self.executionFrame,
            text="Execution",
            icon=OrchestratorIcon.CHEMUNITED,
        )

    def recenter_views(self):
        self.executionGraph.recenter_view()
        self.workflows_protocol.recenter_view()
