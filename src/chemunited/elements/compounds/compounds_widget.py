"""Widget for project compound definitions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from .compound_list import CompoundList

if TYPE_CHECKING:
    from chemunited.setup import SetupWindow


class CompoundsWidget(QWidget):
    def __init__(self, parent: "SetupWindow" | None = None) -> None:
        super().__init__(parent)
        self.parent_ref = parent
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.compound_list = CompoundList(self)
        layout.addWidget(self.compound_list, stretch=1)

    def showEvent(self, a0) -> None:
        super().showEvent(a0)
        self.compound_list.sync()

    def sync(self) -> None:
        self.compound_list.sync()

    def selected_name(self) -> str | None:
        return self.compound_list.selected_name()

    def visible_names(self) -> list[str]:
        return self.compound_list.visible_names()

    @property
    def list_widget(self):
        return self.compound_list.list_widget
