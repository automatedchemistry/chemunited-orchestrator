from __future__ import annotations

import typing

from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import FluentIcon, LineEdit, PrimaryPushButton, TransparentToolButton

from .base_card import BaseFieldCard


class ListFieldCard(BaseFieldCard):
    """Card for `list[str]` or `list[float]` fields with dynamic add/remove rows."""

    def _type_badge(self) -> str:
        inner = self._inner_type()
        name = getattr(inner, "__name__", str(inner))
        return f"list[{name}]"

    def _inner_type(self) -> type:
        args = typing.get_args(self._field_info.annotation)
        return args[0] if args else str

    def _build_input(self) -> QWidget:
        self._container = QWidget(self)
        self._rows_layout = QVBoxLayout(self._container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(4)

        self._add_btn = PrimaryPushButton("+ Add item")
        self._add_btn.clicked.connect(self._add_row)
        self._rows_layout.addWidget(self._add_btn)

        self._row_widgets: list[tuple[LineEdit, QWidget]] = []
        return self._container

    def _add_row(self, value: str = "") -> None:
        row_widget = QWidget(self._container)
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(4)

        edit = LineEdit()
        edit.setClearButtonEnabled(True)
        edit.setText(str(value) if value else "")
        edit.textChanged.connect(lambda _: self._clear_error())

        del_btn = TransparentToolButton(FluentIcon.DELETE)
        del_btn.clicked.connect(lambda: self._remove_row(row_widget, edit))

        row_layout.addWidget(edit)
        row_layout.addWidget(del_btn)

        # Insert before the "Add item" button
        self._rows_layout.insertWidget(self._rows_layout.count() - 1, row_widget)
        self._row_widgets.append((edit, row_widget))

    def _remove_row(self, row_widget: QWidget, edit: LineEdit) -> None:
        self._row_widgets = [(e, w) for e, w in self._row_widgets if w is not row_widget]
        self._rows_layout.removeWidget(row_widget)
        row_widget.deleteLater()
        self._clear_error()

    def get_value(self) -> list:
        inner = self._inner_type()
        result = []
        for edit, _ in self._row_widgets:
            text = edit.text()
            try:
                result.append(inner(text))
            except (ValueError, TypeError):
                result.append(text)
        return result

    def set_value(self, value) -> None:
        # Clear existing rows
        for _, row_widget in self._row_widgets:
            self._rows_layout.removeWidget(row_widget)
            row_widget.deleteLater()
        self._row_widgets = []

        for item in (value or []):
            self._add_row(str(item))

    def validate(self) -> bool:
        for edit, _ in self._row_widgets:
            if not edit.text().strip():
                self._set_error("Items must not be empty")
                return False

        inner = self._inner_type()
        if inner is float or inner is int:
            for edit, _ in self._row_widgets:
                try:
                    inner(edit.text())
                except ValueError:
                    self._set_error(f"All items must be valid {inner.__name__} values")
                    return False

        self._mark_valid()
        return True
