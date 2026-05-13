from chemunited.qt.shared.prcess_list import ProcessList, ProcessWidget
from PyQt5.QtWidgets import QAbstractItemView
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chemunited.qt.monitor import MonitorWindow

class MonitorProcessList(ProcessList):
    def __init__(self, data: dict, parent=None):
        super().__init__(data, parent)
        self.set_items_renameable(False)
        self._list_widget.setDragDropMode(QAbstractItemView.NoDragDrop)


class MonitorProcessesWidget(ProcessWidget):
    def __init__(self, parent: "MonitorWindow"):
        super().__init__(
            process_list=MonitorProcessList(parent.orchestrator.protocols, parent),
            parent=parent,
        )
        self.parent_ref = parent
        self._connect_signals()
    
    def _connect_signals(self) -> None:
        orch = self.parent_ref.orchestrator
        self._list.selection_changed.connect(orch.select_process)