"""Widget of compounds and component inventory status."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import FluentIcon, PrimaryPushButton

from .compound_list import CompoundList
from .iventory_status import InventoryStatusDialog

if TYPE_CHECKING:
    from chemunited.setup import SetupWindow


class CompoundsWidget(QWidget):
    def __init__(self, parent: "SetupWindow" | None = None) -> None:
        super().__init__(parent)
        self.parent_ref = parent
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.compound_list = CompoundList(self)
        layout.addWidget(self.compound_list, stretch=1)

        action_row = QHBoxLayout()
        action_row.setContentsMargins(24, 0, 24, 18)
        self.edit_inventory_button = PrimaryPushButton(
            FluentIcon.EDIT,
            "Edit inventories",
            self,
        )
        self.edit_inventory_button.setToolTip(
            "Edit the initial inventory content of components"
        )
        action_row.addWidget(
            self.edit_inventory_button,
            alignment=Qt.AlignLeft,  # type: ignore[arg-type]
        )
        action_row.addStretch()
        layout.addLayout(action_row)

    def _connect_signals(self) -> None:
        self.edit_inventory_button.clicked.connect(  # type: ignore[attr-defined]
            self._open_inventory_dialog
        )

    def showEvent(self, event) -> None:
        super().showEvent(event)
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

    def _open_inventory_dialog(self) -> None:
        dialog = InventoryStatusDialog(
            component_provider=self._component_items,
            parent=self.window(),
        )
        dialog.exec_()

    def _component_items(self):
        orchestrator = getattr(self.parent_ref, "orchestrator", None)
        components = getattr(orchestrator, "components", None)
        if components is None:
            return []
        return components.items()
