from __future__ import annotations

import subprocess
import sys
from typing import TYPE_CHECKING

from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import QPlainTextEdit, QVBoxLayout
from qfluentwidgets import FluentIcon, PushButton, StrongBodyLabel
from qframelesswindow import FramelessDialog

if TYPE_CHECKING:
    from chemunited.utils.version_check import UpdateAvailable


class PipUpgradeThread(QThread):
    output_line: pyqtSignal = pyqtSignal(str)
    finished_with_code: pyqtSignal = pyqtSignal(int)

    def __init__(self, packages: list[str], parent=None) -> None:
        super().__init__(parent)
        self._packages = packages

    def run(self) -> None:
        proc = subprocess.Popen(
            [sys.executable, "-m", "pip", "install", "--upgrade", *self._packages],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            self.output_line.emit(line.rstrip())
        proc.wait()
        self.finished_with_code.emit(proc.returncode)


class UpdateDialog(FramelessDialog):
    def __init__(self, updates: list[UpdateAvailable], parent=None) -> None:
        super().__init__(parent=parent)
        self.setWindowTitle("Update Packages")
        self.setResizeEnabled(True)

        packages = [u.package for u in updates]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, self.titleBar.height() + 16, 16, 16)
        layout.setSpacing(12)

        self._header = StrongBodyLabel("Installing updates…", self)
        layout.addWidget(self._header)

        self._output = QPlainTextEdit(self)
        self._output.setReadOnly(True)
        self._output.setMinimumHeight(300)
        self._output.setMinimumWidth(520)
        layout.addWidget(self._output)

        self._close_btn = PushButton(FluentIcon.CLOSE, "Close", self)
        self._close_btn.setEnabled(False)
        self._close_btn.clicked.connect(self.accept)
        layout.addWidget(self._close_btn)

        self._thread = PipUpgradeThread(packages, parent=self)
        self._thread.output_line.connect(self._append_line)
        self._thread.finished_with_code.connect(self._on_finished)
        self._thread.start()

    def _append_line(self, line: str) -> None:
        self._output.appendPlainText(line)

    def _on_finished(self, returncode: int) -> None:
        if returncode == 0:
            self._header.setText("Done")
            self._output.appendPlainText("\n✓ Done. Please restart ChemUnited.")
        else:
            self._header.setText("Failed")
            self._output.appendPlainText(
                f"\n✗ pip exited with code {returncode}.\n "
                "Please check the output above for details and try updating manually. "
            )
        self._close_btn.setEnabled(True)
