from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QListWidgetItem, QVBoxLayout, QWidget
from qfluentwidgets import FluentIcon, StrongBodyLabel

from chemunited.qt.shared.icon import OrchestratorIcon
from chemunited.qt.shared.prcess_list import ProcessItem, ProcessList

if TYPE_CHECKING:
    from chemunited.qt.setup import SetupWindow


class AvailableProcessList(ProcessList):
    """Available protocol catalogue for pre-run selection."""

    activate_requested = pyqtSignal(str)

    def __init__(self, data: dict, parent: QWidget | None = None) -> None:
        super().__init__(data, parent)
        self.add_items_option("Activate", FluentIcon.ADD, "Add this process to Active")
        self._dispatch["Activate"] = self._on_activate

    def _on_activate(self, name: str) -> None:
        self.activate_requested.emit(name)  # type: ignore[attr-defined]


class ActiveProcessList(ProcessList):
    """Ordered list of processes selected for execution."""

    access_parameters_requested = pyqtSignal(str)
    remove_requested = pyqtSignal(str)

    def __init__(self, data: dict, parent: QWidget | None = None) -> None:
        super().__init__(data, parent)
        self.add_items_option(
            "Process Parameters",
            OrchestratorIcon.VARIABLE.icon(),
            "Access process parameters",
        )
        self.add_items_option(
            "Remove from Active",
            FluentIcon.DELETE,
            "Remove this process from Active",
        )
        self._dispatch["Process Parameters"] = self._on_process_parameters
        self._dispatch["Remove from Active"] = self._on_remove

    def _on_process_parameters(self, name: str) -> None:
        self.access_parameters_requested.emit(name)  # type: ignore[attr-defined]

    def _on_remove(self, name: str) -> None:
        self.remove_requested.emit(name)  # type: ignore[attr-defined]

    def names(self) -> list[str]:
        result = []
        for i in range(self._list_widget.count()):
            active_name = self._list_widget.item(i).data(Qt.UserRole)
            if active_name is not None:
                result.append(str(active_name))
        return result

    def sync(self) -> None:
        data_keys = set(self._data.keys())
        list_names = set(self.names())

        for name in list_names - data_keys:
            for i in range(self._list_widget.count()):
                list_item = self._list_widget.item(i)
                if list_item.data(Qt.UserRole) == name:
                    self._list_widget.takeItem(i)
                    break

        for name in data_keys - list_names:
            self._create_and_add_item(name)

    def _create_and_add_item(self, name: str) -> None:
        process_name = self._data.get(name, name)
        item = ProcessItem(str(process_name))
        for opt_name, opt_icon, opt_tip in self._option_specs:
            item.add_option(opt_name, opt_icon, opt_tip)

        item.option_triggered.connect(
            lambda option_name, _process_name, active_name=name: (
                self.remove_requested.emit(active_name)  # type: ignore[attr-defined]
                if option_name == "Remove from Active"
                else self.access_parameters_requested.emit(str(process_name))  # type: ignore[attr-defined]
            )
        )

        list_item = QListWidgetItem()
        list_item.setData(Qt.UserRole, name)
        list_item.setSizeHint(item.sizeHint())
        self._list_widget.addItem(list_item)
        self._list_widget.setItemWidget(list_item, item)


class ProcessDoubleList(QWidget):
    """Pre-run process chooser with Available and Active lists."""

    def __init__(self, parent: SetupWindow):
        super().__init__(parent=parent)
        self.parent_ref = parent
        self._active_data: dict[str, str] = {}
        self._active_index = 0

        self.available_list = AvailableProcessList(
            parent.orchestrator.protocols,
            parent=self,
        )
        self.active_list = ActiveProcessList(self._active_data, parent=self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        layout.addWidget(StrongBodyLabel("Available", parent=self))
        layout.addWidget(self.available_list, stretch=1)
        layout.addWidget(StrongBodyLabel("Active", parent=self))
        layout.addWidget(self.active_list, stretch=1)

        self.connect_signals()
        self.sync_lists()

    def connect_signals(self) -> None:
        self.available_list.activate_requested.connect(self._activate_process)
        self.active_list.remove_requested.connect(self._remove_active_process)
        self.active_list.access_parameters_requested.connect(
            self.parent_ref.orchestrator.access_process_parameters
        )

    def _activate_process(self, name: str) -> None:
        protocols = self.parent_ref.orchestrator.protocols
        if name not in protocols:
            return
        self._active_index += 1
        self._active_data[f"{name}_{self._active_index}"] = name
        self.sync_lists()

    def _remove_active_process(self, name: str) -> None:
        self._active_data.pop(name, None)
        self.sync_lists()

    def sync_lists(self) -> None:
        self.available_list.sync()
        available_names = set(self.available_list.names())
        for active_name, process_name in list(self._active_data.items()):
            if process_name not in available_names:
                del self._active_data[active_name]
        self.active_list.sync()
