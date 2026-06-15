from __future__ import annotations

from collections.abc import Callable

from loguru import logger
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QAbstractItemView, QListWidgetItem, QVBoxLayout, QWidget
from qfluentwidgets import ListWidget

from .item import ProcessItem


class ProcessList(QWidget):
    """Foundation class designed to be subclassed. Owns all logic and dispatch."""

    selection_changed = pyqtSignal(str)  # name of selected item, or "" if deselected
    process_renamed = pyqtSignal(str, str)  # (old_name, new_name)

    def __init__(self, data: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._data = data
        self._option_specs: list[tuple] = []  # (name, icon, tip)
        self._rename_enabled: bool = False
        self._editing_item: ProcessItem | None = None
        self._dispatch: dict[str, Callable[[str], None]] = {}

        self._list_widget = ListWidget(self)
        self._list_widget.setDragDropMode(QAbstractItemView.InternalMove)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._list_widget)

        self._list_widget.currentItemChanged.connect(self._on_selection_changed)  # type: ignore[attr-defined]
        self.sync()

    # ------------------------------------------------------------------
    # Internal slots
    # ------------------------------------------------------------------

    def _on_selection_changed(self, current, previous) -> None:
        if current is None:
            self.selection_changed.emit("")  # type: ignore[attr-defined]
            return
        widget = self._list_widget.itemWidget(current)
        self.selection_changed.emit(widget.name if widget is not None else "")  # type: ignore[attr-defined]

    def _on_edit_started(self, process_name: str) -> None:
        new_item: ProcessItem | None = None
        for i in range(self._list_widget.count()):
            list_item = self._list_widget.item(i)
            widget = self._list_widget.itemWidget(list_item)
            if widget is not None and widget.name == process_name:
                new_item = widget
                break

        if self._editing_item is not None and self._editing_item is not new_item:
            self._editing_item._exit_edit_mode(confirm=False)
        self._editing_item = new_item

    def _on_rename_requested(self, current_name: str, proposed_name: str) -> None:
        self.process_renamed.emit(current_name, proposed_name)  # type: ignore[attr-defined]
        self._editing_item = None

    def _on_option_triggered(self, option_name: str, process_name: str) -> None:
        handler = self._dispatch.get(option_name)
        if handler is None:
            logger.warning(f"No handler registered for option '{option_name}'.")
            return
        handler(process_name)

    # ------------------------------------------------------------------
    # Configuration methods - call in subclass __init__
    # ------------------------------------------------------------------

    def set_items_renameable(self, enabled: bool) -> None:
        self._rename_enabled = enabled
        if enabled:
            for i in range(self._list_widget.count()):
                list_item = self._list_widget.item(i)
                widget = self._list_widget.itemWidget(list_item)
                if widget is not None:
                    widget.enable_rename()

    def add_items_option(self, name: str, icon, tip: str) -> None:
        self._option_specs.append((name, icon, tip))
        for i in range(self._list_widget.count()):
            list_item = self._list_widget.item(i)
            widget = self._list_widget.itemWidget(list_item)
            if widget is not None:
                widget.add_option(name, icon, tip)

    # ------------------------------------------------------------------
    # Access / helpers
    # ------------------------------------------------------------------

    def selected_name(self) -> str | None:
        current = self._list_widget.currentItem()
        if current is None:
            return None
        widget = self._list_widget.itemWidget(current)
        return widget.name if widget is not None else None

    def names(self) -> list[str]:
        result = []
        for i in range(self._list_widget.count()):
            list_item = self._list_widget.item(i)
            widget = self._list_widget.itemWidget(list_item)
            if widget is not None:
                result.append(widget.name)
        return result

    def sync(self) -> None:
        data_keys = set(self._data.keys())
        list_names = set(self.names())

        for name in list_names - data_keys:
            for i in range(self._list_widget.count()):
                list_item = self._list_widget.item(i)
                widget = self._list_widget.itemWidget(list_item)
                if widget is not None and widget.name == name:
                    self._remove_row(i)
                    break

        for name in data_keys - list_names:
            self._create_and_add_item(name)

    def _create_and_add_item(self, name: str) -> ProcessItem | None:
        item = ProcessItem(name)
        if self._rename_enabled:
            item.enable_rename()
        for opt_name, opt_icon, opt_tip in self._option_specs:
            item.add_option(opt_name, opt_icon, opt_tip)

        item.edit_started.connect(self._on_edit_started)  # type: ignore[attr-defined]
        item.rename_requested.connect(self._on_rename_requested)  # type: ignore[attr-defined]
        item.option_triggered.connect(self._on_option_triggered)  # type: ignore[attr-defined]

        list_item = QListWidgetItem()
        list_item.setSizeHint(item.sizeHint())
        self._list_widget.addItem(list_item)
        self._list_widget.setItemWidget(list_item, item)
        return item

    def _remove_row(self, row: int) -> None:
        list_item = self._list_widget.item(row)
        if list_item is None:
            return
        widget = self._list_widget.itemWidget(list_item)
        if widget is not None:
            self._list_widget.removeItemWidget(list_item)
            widget.setParent(None)
            widget.deleteLater()
        self._list_widget.takeItem(row)
