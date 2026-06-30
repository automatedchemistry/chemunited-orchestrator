from typing import TYPE_CHECKING

from PyQt5.QtWidgets import QFrame, QHBoxLayout
from qfluentwidgets import FluentIcon

from chemunited.shared.enums import SetupStepMode
from chemunited.shared.icon import OrchestratorIcon
from chemunited.shared.widgets.segment_widget import SegmentWindow

from .dashboard_launcher import DashBoardLauncherFrame
from .process_list import ProcessDoubleList
from .protocols_historic import ProtocolsManageList

if TYPE_CHECKING:
    from chemunited.setup import SetupWindow


class PreRunFrame(QFrame):

    def __init__(self, parent: "SetupWindow"):
        super().__init__(parent)
        self.classification = SetupStepMode.PRE_RUN
        self.parent_ref = parent
        self.main_layout = QHBoxLayout(self)

        self.desktop_conf = QFrame(self)
        self.processes_list_widget = ProcessDoubleList(parent=parent)
        self.protocols_list_widget = ProtocolsManageList(parent=parent)

        self.DashBoardLauncherFrame = DashBoardLauncherFrame(self)

        self.segment_window = SegmentWindow(self)

        # Signal connections
        self.segment_window.current_widget_changed.connect(  # type: ignore[attr-defined]
            self._on_current_widget_changed
        )

        self.init_ui()

    def init_ui(self):

        desktop_layout = QHBoxLayout(self.desktop_conf)
        desktop_layout.addWidget(self.processes_list_widget)
        desktop_layout.addWidget(self.protocols_list_widget)

        self.segment_window.addSubInterface(
            widget=self.desktop_conf,
            objectName="desktop_conf",
            text="Pre-Execute internally",
            icon=FluentIcon.ACCEPT_MEDIUM.path(),
        )

        self.segment_window.addSubInterface(
            widget=self.DashBoardLauncherFrame,
            objectName="DashBoardLauncherFrame",
            text="Dashboard Launcher",
            icon=OrchestratorIcon.ROUTER.path(),
        )

        self.main_layout.addWidget(self.segment_window)

    def sync(self):
        self.processes_list_widget.sync_lists()
        self.protocols_list_widget.fill_cards()

    def _on_current_widget_changed(self, name: str) -> None:
        if name == "DashBoardLauncherFrame":
            self.DashBoardLauncherFrame.refresh_status()
