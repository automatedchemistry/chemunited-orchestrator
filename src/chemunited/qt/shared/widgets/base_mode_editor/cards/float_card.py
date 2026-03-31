from __future__ import annotations

import math

from PyQt5.QtWidgets import QWidget
from qfluentwidgets import DoubleSpinBox

from .base_card import BaseFieldCard

_FLOAT_MAX = 1e18


class FloatFieldCard(BaseFieldCard):
    """Card for `float` fields. Extracts Ge/Le bounds and step from field metadata."""

    def _type_badge(self) -> str:
        return "float"

    def _build_input(self) -> QWidget:
        self._spinbox = DoubleSpinBox()
        self._spinbox.setRange(-_FLOAT_MAX, _FLOAT_MAX)
        extras = self._field_info.json_schema_extra or {}
        self._spinbox.setSingleStep(float(extras.get("step", 0.01)))
        self._spinbox.setDecimals(6)
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
                self._spinbox.setMinimum(float(constraint.ge))
            elif isinstance(constraint, Le):
                self._spinbox.setMaximum(float(constraint.le))

    def get_value(self) -> float:
        return self._spinbox.value()

    def set_value(self, value) -> None:
        self._spinbox.setValue(float(value))

    def validate(self) -> bool:
        value = self._spinbox.value()

        if not math.isfinite(value):
            self._set_error("Value must be a finite number")
            return False

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
