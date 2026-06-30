from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from chemunited_workflow.enums import NodeState
from loguru import logger
from pydantic import BaseModel, ValidationError
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QListWidgetItem, QVBoxLayout, QWidget
from qfluentwidgets import (
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    PushButton,
    StrongBodyLabel,
)

from chemunited.protocols.workflows.naming import process_config_class_name
from chemunited.shared.icon import OrchestratorIcon
from chemunited.shared.prcess_list import ProcessItem, ProcessList
from chemunited.shared.widgets.base_mode_editor.dialog import BaseModeDialog
from chemunited.utils.files import load_class

if TYPE_CHECKING:
    from chemunited.protocols.workflows import ProcessWorkflow
    from chemunited.setup import SetupWindow


class AvailableProcessList(ProcessList):
    """Available protocol catalogue for pre-run selection.

    The ``data`` mapping is the orchestrator protocol registry:
    ``{process_name: ProcessWorkflow}``. Its keys are the selectable process
    names shown in the list and emitted by ``activate_requested``.
    """

    activate_requested = pyqtSignal(str)

    def __init__(
        self,
        data: dict[str, ProcessWorkflow],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(data, parent)
        self.add_items_option("Activate", FluentIcon.ADD, "Add this process to Active")
        self._dispatch["Activate"] = self._on_activate

    def _on_activate(self, name: str) -> None:
        self.activate_requested.emit(name)  # type: ignore[attr-defined]


class ActiveProcessList(ProcessList):
    """Ordered list of process instances selected for execution.

    The ``data`` mapping is ``{active_name: process_name}``, for example
    ``{"React_1": "React"}``. ``active_name`` is the unique execution
    instance stored on the list item, while ``process_name`` is the base
    process name displayed to the user.
    """

    access_parameters_requested = pyqtSignal(str)
    remove_requested = pyqtSignal(str)

    def __init__(
        self,
        data: dict[str, str],
        parent: QWidget | None = None,
    ) -> None:
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
            active_name = self._list_widget.item(i).data(Qt.UserRole)  # type: ignore[attr-defined]
            if active_name is not None:
                result.append(str(active_name))
        return result

    def sync(self) -> None:
        data_keys = set(self._data.keys())
        list_names = set(self.names())

        for name in list_names - data_keys:
            for i in range(self._list_widget.count()):
                list_item = self._list_widget.item(i)
                if list_item and list_item.data(Qt.UserRole) == name:  # type: ignore[attr-defined]
                    self._remove_row(i)
                    break

        for name in self._data:
            if name in list_names:
                continue
            self._create_and_add_item(name)

    def set_processes(self, processes: list[tuple[str, str]]) -> None:
        self._data.clear()
        self._data.update(processes)
        while self._list_widget.count():
            self._remove_row(0)
        self.sync()

    def process_item(self, active_name: str) -> ProcessItem | None:
        for i in range(self._list_widget.count()):
            list_item = self._list_widget.item(i)
            if list_item and list_item.data(Qt.UserRole) == active_name:  # type: ignore[attr-defined]
                widget = self._list_widget.itemWidget(list_item)
                if isinstance(widget, ProcessItem):
                    return widget
        return None

    def set_process_status(self, active_name: str, status) -> bool:
        item = self.process_item(active_name)
        if item is None:
            return False
        item.set_status(status)
        return True

    def reset_statuses(self, status=NodeState.NOT_VISITED) -> None:
        for i in range(self._list_widget.count()):
            list_item = self._list_widget.item(i)
            widget = self._list_widget.itemWidget(list_item)
            if isinstance(widget, ProcessItem):
                widget.set_status(status)

    def _create_and_add_item(self, name: str) -> ProcessItem:
        process_name = self._data.get(name, name)
        item = ProcessItem(str(process_name))
        for opt_name, opt_icon, opt_tip in self._option_specs:
            item.add_option(opt_name, opt_icon, opt_tip)

        item.option_triggered.connect(  # type: ignore[attr-defined]
            lambda option_name, _process_name, active_name=name: (
                self.remove_requested.emit(active_name)  # type: ignore[attr-defined]
                if option_name == "Remove from Active"
                else self.access_parameters_requested.emit(active_name)  # type: ignore[attr-defined]
            )
        )

        list_item = QListWidgetItem()
        list_item.setData(Qt.UserRole, name)  # type: ignore[attr-defined]
        list_item.setSizeHint(item.sizeHint())
        self._list_widget.addItem(list_item)
        self._list_widget.setItemWidget(list_item, item)
        return item


class ProcessDoubleList(QWidget):
    """Pre-run process chooser with Available and Active lists."""

    def __init__(self, parent: SetupWindow):
        super().__init__(parent=parent)
        self.parent_ref = parent
        self._active_data: dict[str, str] = {}
        self._active_index = 0
        self._main_parameters_instance: BaseModel | None = None
        self._process_parameter_instances: dict[str, BaseModel] = {}

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

        button_layout = QVBoxLayout()
        button_layout.setContentsMargins(0, 4, 0, 0)
        button_layout.setSpacing(6)

        self.main_params_button = PushButton(
            OrchestratorIcon.VARIABLE.icon(), "Main Parameters"
        )
        button_layout.addWidget(self.main_params_button)

        self.run_monitoring_button = PushButton(
            OrchestratorIcon.CHEMUNITED.icon(), "Run Monitoring"
        )
        self.run_monitoring_button.setEnabled(False)
        self.run_monitoring_button.setToolTip("Run monitoring is not available yet")
        button_layout.addWidget(self.run_monitoring_button)

        self.run_simulation_button = PushButton(
            OrchestratorIcon.CHEMUNITED_SIMU.icon(), "Run Simulation"
        )
        self.run_simulation_button.setEnabled(False)
        self.run_simulation_button.setToolTip("Run simulation is not available yet")
        button_layout.addWidget(self.run_simulation_button)

        self.save_button = PushButton(FluentIcon.SAVE.icon(), "Save Protocols Script")
        button_layout.addWidget(self.save_button)
        layout.addLayout(button_layout)

        self.connect_signals()
        self.sync_lists()

    def connect_signals(self) -> None:
        self.available_list.activate_requested.connect(self._activate_process)  # type: ignore[attr-defined]
        self.active_list.remove_requested.connect(self._remove_active_process)  # type: ignore[attr-defined]
        self.active_list.access_parameters_requested.connect(self.process_parameters_dialog)  # type: ignore[attr-defined]
        self.main_params_button.clicked.connect(self.main_parameters_dialog)  # type: ignore[attr-defined]
        self.save_button.clicked.connect(self.save_protocols)  # type: ignore[attr-defined]

    def _activate_process(self, name: str) -> None:
        protocols = self.parent_ref.orchestrator.protocols
        if name not in protocols:
            return
        self._active_index += 1
        self._active_data[f"{name}_{self._active_index}"] = name
        self.sync_lists()

    def _remove_active_process(self, name: str) -> None:
        self._active_data.pop(name, None)
        self._process_parameter_instances.pop(name, None)
        self.sync_lists()

    def sync_lists(self) -> None:
        self.available_list.sync()
        available_names = set(self.available_list.names())
        for active_name, process_name in list(self._active_data.items()):
            if process_name not in available_names:
                del self._active_data[active_name]
                self._process_parameter_instances.pop(active_name, None)
        self.active_list.sync()

    def active_processes_in_order(self) -> list[tuple[str, str]]:
        return [
            (active_name, self._active_data[active_name])
            for active_name in self.active_list.names()
            if active_name in self._active_data
        ]

    def main_parameters_dialog(self) -> None:
        instance = self._ensure_main_parameters_instance()
        if instance is None:
            return

        working_dir = self._working_dir()
        if working_dir is None:
            return
        model_class = self._load_parameter_model(
            working_dir / "protocols" / "main_parameters.py",
            "MainParameter",
        )
        if model_class is None:
            return

        dlg = BaseModeDialog(
            model_class=model_class,
            instance=instance,
            title="Main Parameters",
            parent=self,
        )
        if dlg.exec_():
            result = dlg.get_result_instance()
            if result is not None:
                self._main_parameters_instance = result

    def process_parameters_dialog(self, active_name: str) -> None:
        process_name = self._active_data.get(active_name)
        if process_name is None:
            self._show_warning("The selected active process no longer exists.")
            return

        instance = self._ensure_process_parameter_instance(active_name)
        if instance is None:
            return

        working_dir = self._working_dir()
        if working_dir is None:
            return
        path = working_dir / "protocols" / f"{process_name}.py"
        model_class = self._load_process_parameter_model(path, process_name)
        if model_class is None:
            return

        dlg = BaseModeDialog(
            model_class=model_class,
            instance=instance,
            title=f"{process_name} Parameters",
            parent=self,
        )
        if dlg.exec_():
            result = dlg.get_result_instance()
            if result is not None:
                self._process_parameter_instances[active_name] = result

    def _working_dir(self) -> Path | None:
        working_dir = getattr(self.parent_ref.orchestrator, "working_dir", None)
        if working_dir is None:
            self._show_warning("Load or create a project before editing parameters.")
            return None
        return Path(working_dir)

    def _load_parameter_model(
        self,
        path: Path,
        class_name: str,
    ) -> type[BaseModel] | None:
        if not path.is_file():
            self._show_warning(f"Parameter file not found: {path.name}")
            return None

        try:
            model_class = load_class(path, class_name)
            rebuild = getattr(model_class, "model_rebuild", None)
            if callable(rebuild):
                rebuild(force=True)
        except Exception as exc:
            self._show_warning(f"Could not load {class_name}: {exc}")
            return None

        if not isinstance(model_class, type) or not issubclass(
            model_class,
            BaseModel,
        ):
            self._show_warning(f"{class_name} must inherit from pydantic.BaseModel.")
            return None
        return model_class

    def _load_process_parameter_model(
        self,
        path: Path,
        process_name: str,
    ) -> type[BaseModel] | None:
        class_names = (process_config_class_name(process_name),)
        errors: list[str] = []

        for class_name in class_names:
            try:
                model_class = load_class(path, class_name)
                rebuild = getattr(model_class, "model_rebuild", None)
                if callable(rebuild):
                    rebuild(force=True)
            except Exception as exc:
                errors.append(f"{class_name}: {exc}")
                continue

            if not isinstance(model_class, type) or not issubclass(
                model_class,
                BaseModel,
            ):
                errors.append(f"{class_name}: must inherit from pydantic.BaseModel")
                continue

            return model_class

        self._show_warning(
            f"Could not load process parameters from {path.name}: " + "; ".join(errors)
        )
        return None

    def _default_instance(
        self,
        model_class: type[BaseModel],
        path: Path,
    ) -> BaseModel | None:
        try:
            return model_class()
        except ValidationError as exc:
            self._show_warning(f"Could not create parameters from {path.name}: {exc}")
            return None

    def _ensure_main_parameters_instance(self) -> BaseModel | None:
        if self._main_parameters_instance is not None:
            return self._main_parameters_instance

        working_dir = self._working_dir()
        if working_dir is None:
            return None

        path = working_dir / "protocols" / "main_parameters.py"
        model_class = self._load_parameter_model(path, "MainParameter")
        if model_class is None:
            return None

        instance = self._default_instance(model_class, path)
        if instance is None:
            return None

        self._main_parameters_instance = instance
        return instance

    def _ensure_process_parameter_instance(
        self,
        active_name: str,
    ) -> BaseModel | None:
        instance = self._process_parameter_instances.get(active_name)
        if instance is not None:
            return instance

        process_name = self._active_data.get(active_name)
        if process_name is None:
            self._show_warning("The selected active process no longer exists.")
            return None

        working_dir = self._working_dir()
        if working_dir is None:
            return None

        path = working_dir / "protocols" / f"{process_name}.py"
        model_class = self._load_process_parameter_model(path, process_name)
        if model_class is None:
            return None

        instance = self._default_instance(model_class, path)
        if instance is None:
            return None

        self._process_parameter_instances[active_name] = instance
        return instance

    def _show_warning(self, message: str) -> None:
        InfoBar.warning(
            title="Pre-run parameters",
            content=message,
            orient=Qt.Horizontal,  # type: ignore[attr-defined]
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=4000,
            parent=self,
        )
        logger.warning(message)

    def save_protocols(self) -> None:
        # Ensure the active processes is not empty
        if not self._active_data:
            self._show_warning("No active processes to save.")
            return

        if self._ensure_main_parameters_instance() is None:
            return

        for active_name in self._active_data:
            if self._ensure_process_parameter_instance(active_name) is None:
                return

        self.parent_ref.orchestrator.save_protocols_historic()
