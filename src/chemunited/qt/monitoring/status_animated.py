from __future__ import annotations

import sys
from collections.abc import Sequence
from typing import Any

from PyQt5.QtCore import QFile, QObject, QTimer
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, ToolButton

from chemunited.qt.shared.icon import OrchestratorIcon

ONLINE_FRAMES = (
    "onlineA.svg",
    "onlineB.svg",
    "onlineC.svg",
    "online.svg",
)
SAMPLE_TIME_MS = 1000


class AnimatedOnlineIcon(QObject):
    def __init__(
        self,
        target: Any,
        parent: QObject | None = None,
        frames: Sequence[str] = ONLINE_FRAMES,
        sample_time_ms: int = SAMPLE_TIME_MS,
    ) -> None:
        object_parent = parent or (target if isinstance(target, QObject) else None)
        super().__init__(object_parent)
        self._target = target
        self._frames = tuple(self._resolve_icon_path(frame) for frame in frames)
        self._current_frame = 0

        self._timer = QTimer(self)
        self._timer.setInterval(sample_time_ms)
        self._timer.timeout.connect(self._show_next_frame)  # type: ignore[attr-defined]

        self._set_icon(0)

    def start(self) -> None:
        self._current_frame = 0
        self._set_icon(self._current_frame)
        self._timer.start()

    def stop(self, reset_to_online: bool = True) -> None:
        self._timer.stop()
        if reset_to_online:
            self._set_icon(len(self._frames) - 1)

    def is_active(self) -> bool:
        return self._timer.isActive()

    def _show_next_frame(self) -> None:
        self._current_frame = (self._current_frame + 1) % len(self._frames)
        self._set_icon(self._current_frame)

    def _set_icon(self, frame_index: int) -> None:
        self._target.setIcon(QIcon(self._frames[frame_index]))

    @staticmethod
    def _resolve_icon_path(file_name: str) -> str:
        resource_path = f":/icons/icons/{file_name}"
        if not QFile.exists(resource_path):
            fallback_path = OrchestratorIcon.ONLINE.path()
            if QFile.exists(fallback_path):
                return fallback_path
            raise FileNotFoundError(resource_path)
        return resource_path


if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = QWidget()
    window.setWindowTitle("Animated Online Icon")

    layout = QVBoxLayout(window)
    layout.addWidget(BodyLabel("Online icon animation", window))

    button = ToolButton(parent=window)
    layout.addWidget(button)

    animation = AnimatedOnlineIcon(button, window)
    animation.start()

    window.show()
    sys.exit(app.exec_())
