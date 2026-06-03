from typing import TYPE_CHECKING

from PyQt5.QtWidgets import QFrame, QHBoxLayout

from chemunited.qt.shared.enums import SetupStepMode

from .process_list import ProcessDoubleList
from .protocols_hystoric import ProtocolsManageList

if TYPE_CHECKING:
    from chemunited.qt.setup import SetupWindow


class PreRunFrame(QFrame):

    def __init__(self, parent: "SetupWindow"):
        super().__init__(parent)
        self.classification = SetupStepMode.PRE_RUN
        self.parent_ref = parent
        self.main_layout = QHBoxLayout(self)

        self.processes_list_widget = ProcessDoubleList(parent=parent)
        self.protocols_list_widget = ProtocolsManageList(parent=parent)

        self.init_ui()

    def init_ui(self):
        self.main_layout.addWidget(self.processes_list_widget)
        self.main_layout.addWidget(self.protocols_list_widget)

    def sync(self):
        self.processes_list_widget.sync_lists()
        self.protocols_list_widget.fill_cards()
