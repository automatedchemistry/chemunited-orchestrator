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
        try:
            from annotated_types import MaxLen, MinLen
        except ImportError:
            MinLen = MaxLen = None  # type: ignore[assignment]

        for constraint in (self._field_info.metadata or []):
            if MinLen is not None and isinstance(constraint, MinLen):
                if len(value) < constraint.min_length:
                    self._set_error(f"Minimum length is {constraint.min_length}")
                    return False
            if MaxLen is not None and isinstance(constraint, MaxLen):
                if len(value) > constraint.max_length:
                    self._set_error(f"Maximum length is {constraint.max_length}")
                    return False

        self._mark_valid()
        return True
