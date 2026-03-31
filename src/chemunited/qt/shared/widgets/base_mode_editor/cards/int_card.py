from __future__ import annotations

from PyQt5.QtWidgets import QWidget
from qfluentwidgets import SpinBox

from .base_card import BaseFieldCard

_INT_MIN = -(2**31)
_INT_MAX = 2**31 - 1


class IntFieldCard(BaseFieldCard):
    """Card for `int` fields. Extracts Ge/Le bounds from field metadata."""

    def _type_badge(self) -> str:
        return "int"

    def _build_input(self) -> QWidget:
        self._spinbox = SpinBox()
        self._spinbox.setRange(_INT_MIN, _INT_MAX)
        self._apply_bounds()
        self._spinbox.valueChanged.connect(lambda _: self._clear_error())
        return self._spinbox

    def _apply_bounds(self) -> None:
        try:
            from annotated_types import Ge, Le
        except ImportError:
            return

        for constraint in (self._field_info.metadata or []):
            if isinstance(constraint, Ge):
                self._spinbox.setMinimum(int(constraint.ge))
            elif isinstance(constraint, Le):
                self._spinbox.setMaximum(int(constraint.le))

    def get_value(self) -> int:
        return self._spinbox.value()

    def set_value(self, value) -> None:
        self._spinbox.setValue(int(value))

    def validate(self) -> bool:
        value = self._spinbox.value()

        try:
            from annotated_types import Ge, Le
        except ImportError:
            self._mark_valid()
            return True

        for constraint in (self._field_info.metadata or []):
            if isinstance(constraint, Ge) and value < constraint.ge:
                self._set_error(f"Value must be \u2265 {constraint.ge}")
                return False
            if isinstance(constraint, Le) and value > constraint.le:
                self._set_error(f"Value must be \u2264 {constraint.le}")
                return False

        self._mark_valid()
        return True
