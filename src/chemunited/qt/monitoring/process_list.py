from typing import TYPE_CHECKING

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QAbstractItemView
from qfluentwidgets import PushButton

from chemunited.qt.pre_run.process_list import ActiveProcessList, AvailableProcessList
from chemunited.qt.shared.icon import OrchestratorIcon
from chemunited.qt.shared.prcess_list import ProcessWidget

if TYPE_CHECKING:
    from chemunited.qt.monitor import MonitorWindow


class MonitorProcessesWidget(ProcessWidget):
    def __init__(self, parent: "MonitorWindow"):
        super().__init__(
            process_list=AvailableProcessList(parent.orchestrator.protocols, parent),
            parent=parent,
        )
        self._parent = parent
        self.parent_ref = parent
        self._list.setHidden(True)
        self.active_list = ActiveProcessList(
            {},  # empty dict for now, will be populated when protocol json is loaded
            parent,
        )
        self.active_list._list_widget.setDragDropMode(QAbstractItemView.NoDragDrop)
        self.active_list._list_widget.setSelectionMode(QAbstractItemView.NoSelection)

        self.main_layout.insertWidget(1, self.active_list, 1)
        self.execute_btn = PushButton(OrchestratorIcon.PLAY, "Execute", self)
        self.execute_btn.setToolTip("Execute selected process")
        self.execute_btn.clicked.connect(self._execute_protocol)  # type: ignore[attr-defined]

        self.main_layout.addWidget(
            self.execute_btn,
            0,
            Qt.AlignHCenter | Qt.AlignBottom,  # type: ignore[attr-defined]
        )
        self._connect_signals()

    def _execute_protocol(self) -> None:
        if self._parent.orchestrator.execute():
            self.execute_btn.setIcon(OrchestratorIcon.STOP)
            self.execute_btn.setText("Stop")
            self.execute_btn.setToolTip("Stop execution")
        else:
            self.execute_btn.setIcon(OrchestratorIcon.PLAY)
            self.execute_btn.setText("Execute")
            self.execute_btn.setToolTip("Execute selected process")

    def _connect_signals(self) -> None:
        orch = self.parent_ref.orchestrator
        self._list.selection_changed.connect(orch.select_process)  # type: ignore[attr-defined]

    def activate_process(self, process_name: str) -> None:
        item = self.active_list._create_and_add_item(process_name)
        if hasattr(item, "_menu_button"):
            item._menu_button.hide()  # type: ignore
