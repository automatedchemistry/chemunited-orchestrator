from loguru import logger as _logger
from PyQt5.QtCore import QUrl
from PyQt5.QtGui import QDesktopServices
from qfluentwidgets import NavigationItemPosition

from .monitoring.execution_api_process import ApiProcess
from .monitoring.graph import ExecutionGraph
from .monitoring.process_list import MonitorProcessesWidget
from .monitoring.status_animated import AnimatedOnlineIcon
from .monitoring.summary import SummaryExecutionWindow
from .orchestrator import Orchestrator
from .protocols.workflows.workflow_widget import WorkflowsWidget
from .shared.enums import SetupStepMode, WindowCategory
from .shared.graph import SceneCore
from .shared.icon import OrchestratorIcon
from .shared.widgets.frame_base import FrameBase
from .shared.widgets.main_window import MainWindowBase
from .shared.widgets.segment_widget import SegmentWindow

logger = _logger.bind(window=WindowCategory.EXECUTION)


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
        self.orchestrator.exposed_logs_class = WindowCategory.EXECUTION

        self.protocols_widget = MonitorProcessesWidget(self)

        self.summary_window = None
        self.summary_window_file = None
        self.api_process: ApiProcess | None = None
        self._connect_execution_inspector_signals()

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

        self.executionFrame.addNavigationAction(
            icon=OrchestratorIcon.LINK,
            text="API link",
            onClick=self._open_api_link,
            tooltip="Show API link",
            position=NavigationItemPosition.BOTTOM,
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
            if self.api_process is not None:
                self.api_process.stop_api()
                self.api_process = None
        else:
            working_dir = self.orchestrator.working_dir
            if working_dir is None:
                logger.error("No project loaded — cannot start API.")
                return
            self.api_process = ApiProcess(
                working_dir, self.FrameLoggings.detail_loggins, self
            )
            self.api_process.api_alive.connect(self._on_api_ping)
            if not self.api_process.start_api():
                self.api_process = None
                return
            if self.status_animation is None:
                self.status_animation = AnimatedOnlineIcon(self.status_widget, self)
            self.status_animation.start()
            self.status_widget.setText("Online")
            self.status_widget.setToolTip("Disconnect components")

    def _open_api_link(self):
        if self.api_process is not None:
            QDesktopServices.openUrl(QUrl(self.api_process.url))
        else:
            logger.warning("No API running — connect first.")

    def _on_api_ping(self, alive: bool):
        if alive:
            self.status_widget.setIcon(OrchestratorIcon.ONLINE)
            self.status_widget.setToolTip("API alive — disconnect components")
        else:
            self.status_widget.setIcon(OrchestratorIcon.OFFLINE)
            self.status_widget.setToolTip("API unreachable — reconnect?")

    def closeEvent(self, event):
        if self.api_process is not None:
            self.api_process.stop_api()
        super().closeEvent(event)

    def recenter_views(self):
        self.executionGraph.recenter_view()
        self.workflows_protocol.recenter_view()

    def show_summary(self):
        window = self._ensure_summary_window()
        if window is None:
            return
        self._show_summary_window(window)

    def _connect_execution_inspector_signals(self) -> None:
        self.orchestrator.protocol_execution_started.connect(  # type: ignore[attr-defined]
            self._on_protocol_execution_started
        )
        self.orchestrator.protocol_execution_finished.connect(  # type: ignore[attr-defined]
            self._on_protocol_execution_finished
        )
        self.orchestrator.run_stream_event_received.connect(  # type: ignore[attr-defined]
            self._on_run_stream_event_received
        )
        self.orchestrator.run_report_received.connect(  # type: ignore[attr-defined]
            self._on_run_report_received
        )

    def _ensure_summary_window(self):
        file = self.orchestrator.project_protocol_script_dir
        if file is None:
            logger.error("No project protocol script directory found.")
            return None

        if self.summary_window is None or self.summary_window_file != file:
            self.summary_window = SummaryExecutionWindow.inspect_file(file)
            self.summary_window_file = file if self.summary_window is not None else None
        return self.summary_window

    def _show_summary_window(self, window) -> None:
        window.show()
        window.raise_()
        window.activateWindow()

    def _on_protocol_execution_started(self, run_id: str) -> None:
        window = self._ensure_summary_window()
        if window is None:
            return
        window.start_run(run_id)
        self._show_summary_window(window)

    def _on_protocol_execution_finished(self, state: str) -> None:
        if self.summary_window is not None:
            self.summary_window.finish_run(state)

    def _on_run_stream_event_received(self, run_id: str, payload) -> None:
        if self.summary_window is not None and isinstance(payload, dict):
            self.summary_window.append_stream_event(run_id, payload)

    def _on_run_report_received(self, run_id: str, report) -> None:
        if self.summary_window is not None:
            self.summary_window.set_report(
                run_id,
                report if isinstance(report, dict) else None,
            )
