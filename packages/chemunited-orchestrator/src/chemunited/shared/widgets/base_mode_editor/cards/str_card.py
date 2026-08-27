from __future__ import annotations

from PyQt5.QtWidgets import QWidget
from qfluentwidgets import LineEdit

from .base_card import BaseFieldCard


class StrFieldCard(BaseFieldCard):
    """Card for `str` fields. Uses a clearable LineEdit."""

    def _type_badge(self) -> str:
        return "str"

    def _build_input(self) -> QWidget:
        self._line_edit = LineEdit()
        self._line_edit.setClearButtonEnabled(True)
        self._line_edit.textChanged.connect(lambda _: self._clear_error())
        return self._line_edit

    def get_value(self) -> str:
        return self._line_edit.text()

    def set_value(self, value) -> None:
        self._line_edit.setText(str(value) if value is not None else "")

    def validate(self) -> bool:
        value = self._line_edit.text()
        min_len_type = None
        max_len_type = None
        try:
            from annotated_types import MaxLen, MinLen

            min_len_type = MinLen
            max_len_type = MaxLen
        except ImportError:
            pass

        for constraint in self._field_info.metadata or []:
            if min_len_type is not None and isinstance(constraint, min_len_type):
                if len(value) < constraint.min_length:
                    self._set_error(f"Minimum length is {constraint.min_length}")
                    return False
            if max_len_type is not None and isinstance(constraint, max_len_type):
                if len(value) > constraint.max_length:
                    self._set_error(f"Maximum length is {constraint.max_length}")
                    return False

        self._mark_valid()
        return True
