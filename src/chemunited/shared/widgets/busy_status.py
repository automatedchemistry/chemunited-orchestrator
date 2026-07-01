from __future__ import annotations

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QWidget
from qfluentwidgets import StateToolTip


class BusyStatusController:
    """Small wrapper around StateToolTip for window-level busy feedback."""

    def __init__(self, parent: QWidget) -> None:
        self.parent = parent
        self.tooltip: StateToolTip | None = None
        self.last_title = ""
        self.last_content = ""
        self.last_failed = False

    @property
    def is_active(self) -> bool:
        return self.tooltip is not None

    def show(self, title: str, content: str) -> None:
        self._close_current()
        self.last_title = title
        self.last_content = content
        self.last_failed = False
        self.tooltip = StateToolTip(title, content, self.parent)
        self.tooltip.show()
        self.reposition()

    def update(self, content: str, title: str | None = None) -> None:
        if self.tooltip is None:
            return
        if title is not None:
            self.last_title = title
            self.tooltip.setTitle(title)
        self.last_content = content
        self.tooltip.setContent(content)
        self.reposition()

    def finish(self, content: str) -> None:
        self._complete(content, failed=False)

    def fail(self, content: str) -> None:
        self._complete(content, failed=True)

    def reposition(self) -> None:
        if self.tooltip is None:
            return
        margin = 24
        title_bar = getattr(self.parent, "titleBar", None)
        title_bar_height = title_bar.height() if title_bar is not None else 0
        x = max(margin, self.parent.width() - self.tooltip.width() - margin)
        y = title_bar_height + margin
        self.tooltip.move(x, y)
        self.tooltip.raise_()

    def _complete(self, content: str, failed: bool) -> None:
        tooltip = self.tooltip
        self.last_content = content
        self.last_failed = failed
        if tooltip is None:
            return
        tooltip.setContent(content)
        if failed:
            tooltip.setTitle("Operation failed")
            self.last_title = "Operation failed"
        tooltip.setState(True)
        QTimer.singleShot(1200, lambda: self._clear_if_current(tooltip))

    def _close_current(self) -> None:
        if self.tooltip is None:
            return
        self.tooltip.close()
        self.tooltip = None

    def _clear_if_current(self, tooltip: StateToolTip) -> None:
        if self.tooltip is tooltip:
            self.tooltip = None
