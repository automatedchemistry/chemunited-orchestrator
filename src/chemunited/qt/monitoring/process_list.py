from typing import TYPE_CHECKING

from PyQt5.QtWidgets import QAbstractItemView

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
        self.execute_btn = self.add_bottom_button(
            "Execute",
            OrchestratorIcon.PLAY,
            "Execute selected process",
            self._execute_protocol,
        )
        self.stop_btn = self.add_bottom_button(
            "Stop",
            OrchestratorIcon.STOP,
            "Stop protocol execution",
            self._stop_protocol,
        )
        self._connect_signals()

    def _execute_protocol(self) -> None:
        if self._parent.orchestrator.execute():
            self._set_execution_running(True)

    def _stop_protocol(self) -> None:
        if self._parent.orchestrator.stop_execution():
            self._set_execution_running(False)

    def _set_execution_running(self, running: bool) -> None:
        self.execute_btn.setEnabled(not running)
        self.stop_btn.setEnabled(True)
        if running:
            self.execute_btn.setToolTip("Protocol execution is already running")
            self.stop_btn.setToolTip("Stop protocol execution")
        else:
            self.execute_btn.setToolTip("Execute selected process")
            self.stop_btn.setToolTip("Check for a running protocol and stop it")

    def _connect_signals(self) -> None:
        orch = self.parent_ref.orchestrator
        self._list.selection_changed.connect(orch.select_process)  # type: ignore[attr-defined]
        orch.protocol_execution_started.connect(  # type: ignore[attr-defined]
            lambda _run_id: self._set_execution_running(True)
        )
        orch.protocol_execution_finished.connect(  # type: ignore[attr-defined]
            lambda _state: self._set_execution_running(False)
        )

    def activate_process(self, process_name: str) -> None:
        item = self.active_list._create_and_add_item(process_name)
        if hasattr(item, "_menu_button"):
            item._menu_button.hide()  # type: ignore
