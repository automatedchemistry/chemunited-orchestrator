from typing import TYPE_CHECKING

from PyQt5.QtWidgets import QFrame, QHBoxLayout

from chemunited.shared.enums import SetupStepMode

from .dashboard_launcher import DashBoardLauncherFrame

if TYPE_CHECKING:
    from chemunited.setup import SetupWindow


class PreRunFrame(QFrame):
    """The setup window's Run step: launches the dashboard for the open project.

    Protocols are built, saved, run and watched in the dashboard.
    """

    def __init__(self, parent: "SetupWindow"):
        super().__init__(parent)
        self.classification = SetupStepMode.PRE_RUN
        self.parent_ref = parent
        self.main_layout = QHBoxLayout(self)

        self.DashBoardLauncherFrame = DashBoardLauncherFrame(self)
        self.main_layout.addWidget(self.DashBoardLauncherFrame)

    def sync(self):
        self.DashBoardLauncherFrame.sync()
