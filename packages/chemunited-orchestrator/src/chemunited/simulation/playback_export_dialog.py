"""Basic options for exporting the full simulation playback."""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Sequence

from PySide6.QtWidgets import QDialog, QFormLayout, QHBoxLayout, QVBoxLayout
from qfluentwidgets import (
    BodyLabel,
    ComboBox,
    DoubleSpinBox,
    PrimaryPushButton,
    PushButton,
)

from .playback_export import PlaybackExportOptions, PlaybackFrameSchedule


class PlaybackExportDialog(QDialog):
    def __init__(self, times: Sequence[float], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export animation")
        self.setMinimumWidth(400)
        self._times = tuple(times)
        layout = QVBoxLayout(self)
        description = BodyLabel(
            "Export the full platform and simulation timestamp. Playback uses "
            "recorded snapshots; states are held until the next snapshot.",
            self,
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        form = QFormLayout()
        self.format_combo = ComboBox(self)
        self.format_combo.addItem("MP4", userData="mp4")
        self.format_combo.addItem("GIF", userData="gif")
        form.addRow("Format", self.format_combo)
        self.resolution_combo = ComboBox(self)
        for width, height in ((640, 360), (1280, 720), (1920, 1080)):
            self.resolution_combo.addItem(
                f"{width} × {height}", userData=(width, height)
            )
        self.resolution_combo.setCurrentIndex(1)
        form.addRow("Resolution", self.resolution_combo)
        self.speed_spin = DoubleSpinBox(self)
        self.speed_spin.setRange(0.1, 1000)
        self.speed_spin.setDecimals(1)
        self.speed_spin.setSuffix("×")
        self.speed_spin.setValue(1)
        form.addRow("Playback speed", self.speed_spin)
        layout.addLayout(form)
        self.duration_label = BodyLabel(self)
        layout.addWidget(self.duration_label)
        self.speed_spin.valueChanged.connect(self._update_duration)
        self._update_duration()
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = PushButton("Cancel", self)
        cancel.clicked.connect(self.reject)
        export = PrimaryPushButton("Export…", self)
        export.setDefault(True)
        export.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(export)
        layout.addLayout(buttons)

    @property
    def selected_format(self) -> Literal["mp4", "gif"]:
        return self.format_combo.currentData()

    def options(self, destination: Path) -> PlaybackExportOptions:
        width, height = self.resolution_combo.currentData()
        return PlaybackExportOptions(
            destination, self.selected_format, width, height, self.speed_spin.value()
        )

    def _update_duration(self) -> None:
        schedule = PlaybackFrameSchedule(self._times, self.speed_spin.value())
        self.duration_label.setText(
            f"Estimated duration: {schedule.duration:.2f} s "
            "(includes a 1 s final hold)"
        )
