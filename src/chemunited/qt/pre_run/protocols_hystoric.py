import os
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger
from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    Dialog,
    GroupHeaderCardWidget,
    ScrollArea,
    TransparentPushButton,
    TransparentToolButton,
)

from chemunited.qt.monitor import MonitorWindow
from chemunited.qt.project.storage import ensure_protocols_hystoric_dir
from chemunited.qt.shared.icon import OrchestratorIcon
from chemunited.qt.shared.widgets.logo_window import show_waiting

from .summary_window import SummaryParametersWindow

if TYPE_CHECKING:
    from chemunited.qt.setup import SetupWindow


class FileCard(GroupHeaderCardWidget):
    def __init__(self, parent: "ProtocolsManageList"):
        super().__init__(parent)
        self._parent = parent
        self.setTitle("Protocols Files")
        self.setBorderRadius(8)

        # keep reference to each file card group
        self.files: dict[str, dict] = {}  # {stem: {"file": Path, "widget": QWidget}}
        self.summary_window: dict[str, SummaryParametersWindow] = {}

    def add_card(self, file: Path, ignore_warning: bool = True):
        if file.stem in self.files:
            if not ignore_warning:
                logger.error(
                    f"File already exists: A protocol script with this name '{file.stem}' already exists. "
                    "Remove it before saving a new one with the same name.",
                )
            return

        widget = QWidget()
        layout = QHBoxLayout(widget)

        # Action buttons

        btn_view = TransparentToolButton(OrchestratorIcon.OPEN_FOLDER)
        btn_view.clicked.connect(partial(self.__view_folder, file.parent))  # type: ignore
        btn_view.setToolTip("Open Local File")

        btn_summary = TransparentToolButton(OrchestratorIcon.JSON)
        btn_summary.clicked.connect(partial(self.show_summary, file))  # type: ignore
        btn_summary.setToolTip("Summary")

        btn_open = TransparentToolButton(OrchestratorIcon.CHEMUNITED)
        btn_open.clicked.connect(partial(self._parent.open_monitoring, file))  # type: ignore
        btn_open.setToolTip("Open Monitoring Window")

        btn_open_simu = TransparentToolButton(OrchestratorIcon.CHEMUNITED_SIMU)
        btn_open_simu.clicked.connect(partial(self._parent.open_simulation, file))  # type: ignore
        btn_open_simu.setToolTip("Open Simulation Window")

        btn_remove = TransparentToolButton(OrchestratorIcon.TRASH)
        btn_remove.clicked.connect(partial(self.remove_file, file))  # type: ignore
        btn_remove.setToolTip("Remove/delete the protocol script")

        layout.addWidget(btn_view)
        layout.addWidget(btn_summary)
        layout.addWidget(btn_open)
        layout.addWidget(btn_open_simu)
        layout.addWidget(btn_remove)

        # Add group to card widget
        group = self.addGroup(
            ":/icons/icons/json.svg",
            f"{file.name}",
            f"{file.stem}",
            widget=widget,
        )

        window = SummaryParametersWindow.inspect_file(file_path=file)
        if window:
            self.summary_window[file.stem] = window
        else:
            btn_summary.setVisible(False)
            btn_open.setVisible(False)
            btn_open_simu.setVisible(False)
            warning_btn = TransparentPushButton("File is corrupted!")
            warning_btn.setStyleSheet(
                """
            TransparentPushButton {
                color: #B71C1C;
            }
            TransparentPushButton:hover {
                color: #EF9A9A;
            }
            TransparentPushButton:pressed {
                color: #F44336;
            }
            """
            )
            layout.addWidget(warning_btn)

        # store reference
        self.files[file.stem] = {"file": file, "group": group}

    def show_summary(self, file):
        window = self.summary_window.get(file.stem)
        if window is not None:
            window.show()

    def __view_folder(self, file: Path):
        """Open the file in the OS default program"""
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(file)))

    def remove_file(self, file: Path):
        """Delete the file from disk and remove its card"""
        if file.exists():
            try:
                os.remove(file)
            except Exception as e:
                logger.opt(exception=e).error(
                    "Error removing file: More details go to the loggings window!"
                )
                return

        # remove UI group
        if file.stem in self.files:
            if window := self.summary_window.pop(file.stem, None):
                window.close()
            group = self.files[file.stem]["group"]
            group.setParent(None)  # detach from layout
            group.deleteLater()  # schedule for deletion
            self.files.pop(file.stem)
            self.groupWidgets.remove(group)


class ProtocolsManageList(ScrollArea):
    def __init__(self, parent: "SetupWindow"):
        super().__init__(parent=parent)
        self.parent_ref = parent
        self._monitor_windows: list[MonitorWindow] = []
        self.view = QWidget(self)

        self.vBoxLayout = QVBoxLayout(self.view)

        self.FileCard = FileCard(self)

        self.setWidget(self.view)
        self.setWidgetResizable(True)
        self.setObjectName("ProtocolsManageList")
        self.enableTransparentBackground()

        self.__initLayout()

        self.fill_cards()

    def __initLayout(self):
        self.vBoxLayout.setSpacing(10)
        self.vBoxLayout.setContentsMargins(0, 0, 10, 30)
        self.vBoxLayout.addWidget(
            self.FileCard, 0, Qt.AlignTop  # type: ignore[attr-defined]
        )

    def fill_cards(self):
        if not self.parent_ref.orchestrator.working_dir:
            return

        folder = ensure_protocols_hystoric_dir(self.parent_ref.orchestrator.working_dir)

        for file in folder.glob("*.json"):
            self.FileCard.add_card(file, ignore_warning=True)

        self.__inspect_all()

    def __inspect_all(self):
        # Collect first to avoid "dictionary changed size during iteration"
        to_remove = []

        for entry in self.FileCard.files.values():
            file: Path = entry["file"]
            if not file.is_file():
                to_remove.append(file)

        # Now remove all missing files
        for file in to_remove:
            self.FileCard.remove_file(file)

    def open_monitoring(self, file_path: Path):
        """Open or create a monitoring window for the given protocol file."""
        content = "Do you want to create a new instance to run the monitoring process?"
        dialog = Dialog("Create a new monitoring", content, self)

        if not dialog.exec():
            return  # user cancelled

        self.__open_window_instance(
            monitor=MonitorWindow(),
            file=file_path,
            name="Monitoring",
        )

    def open_simulation(self, file_path: Path):
        """Open or create a simulation window for the given protocol file."""
        ...

    def __open_window_instance(self, monitor: MonitorWindow, file: Path, name: str):
        """Open a new window instance to run the simulation or monitoring process."""

        wait_window = show_waiting(2)

        # Load required scripts
        chemunited_file = Path(
            file.parent.parent.parent, f"{file.parent.parent.name}.chemunited"
        )
        monitor.orchestrator.open_project(chemunited_file)
        monitor.orchestrator.set_project_protocol_script_dir(file)
        wait_window.close()

        # If everything worked, show monitor window
        monitor.show()
        monitor.raise_()  # bring to front
        monitor.activateWindow()
        self._keep_window_instance(monitor)
        logger.success(
            f"Window Instance Opened: A new instance to run the {name} was build successfully!"
        )

    def _keep_window_instance(self, monitor: MonitorWindow) -> None:
        self._monitor_windows.append(monitor)
        monitor.destroyed.connect(  # type: ignore[attr-defined]
            lambda _obj=None, window=monitor: self._forget_window_instance(window)
        )

    def _forget_window_instance(self, monitor: MonitorWindow) -> None:
        if monitor in self._monitor_windows:
            self._monitor_windows.remove(monitor)
