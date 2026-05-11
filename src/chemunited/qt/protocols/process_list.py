from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt5.QtCore import pyqtSignal
from qfluentwidgets import FluentIcon

from chemunited.qt.shared.icon import OrchestratorIcon
from chemunited.qt.shared.prcess_list import ProcessList, ProcessWidget

if TYPE_CHECKING:
    from chemunited.qt.setup import SetupWindow


class ProtocolsList(ProcessList):
    """Process list for protocols. Emits user intentions only — never self-mutates."""

    rename_requested = pyqtSignal(
        str, str
    )  # (old_name, new_name) — forwarded intention
    remove_requested = pyqtSignal(str)  # user chose Remove
    duplicate_requested = pyqtSignal(str)  # user chose Duplicate — original name only
    access_parameters_requested = pyqtSignal(
        str
    )  # user chose Access Process Parameters

    def __init__(self, data: dict, parent=None):
        super().__init__(data, parent)
        self.set_items_renameable(True)
        self.add_items_option("Duplicate", FluentIcon.COPY, "Duplicate this process")
        self.add_items_option("Remove", FluentIcon.DELETE, "Remove this process")
        self.add_items_option(
            "Process Parameters",
            OrchestratorIcon.VARIABLE.icon(),
            "Access process parameters",
        )
        self._dispatch["Duplicate"] = self._on_duplicate
        self._dispatch["Remove"] = self._on_remove
        self._dispatch["Process Parameters"] = self._on_process_parameters

    # ------------------------------------------------------------------
    # Override base: forward rename as an intention instead of self-mutating
    # ------------------------------------------------------------------

    def _on_rename_requested(self, current_name: str, proposed_name: str) -> None:
        self._editing_item = None
        self.rename_requested.emit(current_name, proposed_name)  # type: ignore

    # ------------------------------------------------------------------
    # Dispatch handlers — emit intentions, no mutations
    # ------------------------------------------------------------------

    def _on_remove(self, name: str) -> None:
        self.remove_requested.emit(name)  # type: ignore

    def _on_duplicate(self, name: str) -> None:
        self.duplicate_requested.emit(name)  # type: ignore

    def _on_process_parameters(self, name: str) -> None:
        self.access_parameters_requested.emit(name)  # type: ignore

    # ------------------------------------------------------------------
    # Called by orchestrator after it has mutated the dict
    # ------------------------------------------------------------------

    def sync_list(self) -> None:
        self.sync()


class ProtocolsWidget(ProcessWidget):
    def __init__(self, parent: "SetupWindow"):
        super().__init__(
            process_list=ProtocolsList(parent.orchestrator.protocols, parent),
            parent=parent,
        )
        self.parent_ref = parent
        self.add_separator()
        self.add_bottom_button(
            name="New Process",
            icon=OrchestratorIcon.PROCESS,
            tip="Add a new process",
            callable=lambda: self.parent_ref.orchestrator.add_process(
                self.parent_ref.orchestrator._generate_process_name()
            ),
        )
        self._connect_signals()

    def _connect_signals(self) -> None:
        orch = self.parent_ref.orchestrator
        self._list.selection_changed.connect(orch.select_process)
        self._list.rename_requested.connect(orch.rename_process)
        self._list.remove_requested.connect(orch.remove_process)
        self._list.duplicate_requested.connect(orch.duplicate_process)
        self._list.access_parameters_requested.connect(orch.access_process_parameters)
