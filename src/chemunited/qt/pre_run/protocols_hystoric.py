from functools import partial
from qfluentwidgets import (
    ScrollArea,
    GroupHeaderCardWidget,
    TransparentToolButton,
    Dialog,
    TransparentPushButton,
)

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout
from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QDesktopServices
from typing import TYPE_CHECKING, Optional
from pathlib import Path
from loguru import logger
import os

from chemunited.qt.shared.icon import OrchestratorIcon
from .summary_window import SummaryWindow

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
        self.summary_window: dict[str, SummaryWindow] = {}

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
        btn_view.clicked.connect(partial(self.__view_folder, file.parent))  # type:ignore
        btn_view.setToolTip("Open Local File")

        btn_summary = TransparentToolButton(OrchestratorIcon.JSON)
        btn_summary.clicked.connect(partial(self.show_summary, file))  # type:ignore
        btn_summary.setToolTip("Summary")

        btn_open = TransparentToolButton(OrchestratorIcon.CHEMUNITED)
        btn_open.clicked.connect(partial(self._parent.open_monitoring, file))  # type:ignore
        btn_open.setToolTip("Open Monitoring Window")

        btn_open_simu = TransparentToolButton(OrchestratorIcon.CHEMUNITED_SIMU)
        btn_open_simu.clicked.connect(partial(self._parent.open_simulation, file))  # type:ignore
        btn_open_simu.setToolTip("Open Simulation Window")

        btn_remove = TransparentToolButton(OrchestratorIcon.TRASH)
        btn_remove.clicked.connect(partial(self.remove_file, file))  # type:ignore
        btn_remove.setToolTip("Remove/delete the protocol script")

        layout.addWidget(btn_view)
        layout.addWidget(btn_summary)
        layout.addWidget(btn_open)
        layout.addWidget(btn_open_simu)
        layout.addWidget(btn_remove)

        # Add group to card widget
        group = self.addGroup(
            ":/orchestrator/images/json.svg",
            f"{file.name}",
            f"{file.stem}",
            widget=widget,
        )

        window = SummaryWindow.inspect_file(file_path=file)
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
        self.summary_window[file.stem].show()

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
            self.summary_window[file.stem].close()
            self.summary_window.pop(file.stem)
            group = self.files[file.stem]["group"]
            group.setParent(None)  # detach from layout
            group.deleteLater()  # schedule for deletion
            self.files.pop(file.stem)
            self.groupWidgets.remove(group)


class ProtocolsManageList(ScrollArea):
    def __init__(self, parent: "SetupWindow"):
        super().__init__(parent=parent)
        self.parent_ref = parent
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
            self.FileCard, 0, Qt.AlignTop  # type:ignore[attr-defined]
        )

    def fill_cards(self):
        if not self.parent_ref.orchestrator.working_dir:
            return

        folder = self.parent_ref.orchestrator.working_dir / "protocols_hystoric"
        folder.mkdir(parents=True, exist_ok=True)

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

    def open_monitoring(self, file_path: Optional[Path] = None):
        """Open or create a monitoring window for the given protocol file."""
        ...

    def open_simulation(self, file_path: Optional[Path] = None):
        """Open or create a monitoring window for the given protocol file."""
        ...
