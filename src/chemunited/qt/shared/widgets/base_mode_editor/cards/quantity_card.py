from __future__ import annotations

import math

from PyQt5.QtWidgets import QHBoxLayout, QWidget
from qfluentwidgets import ComboBox, DoubleSpinBox

from chemunited_core.utils import ChemUnitQuantity, ureg

from .base_card import BaseFieldCard
from .._utils import units_for_dimension

_FLOAT_MAX = 1e18


class ChemUnitQuantityCard(BaseFieldCard):
    """Card for ``ChemUnitQuantity`` fields.

    Renders a magnitude ``DoubleSpinBox`` and a unit ``ComboBox`` populated
    with lab-friendly units whose dimensionality matches the field's
    ``ChemQuantityValidator``.
    """

    def _type_badge(self) -> str:
        return "quantity"

    def _build_input(self) -> QWidget:
        container = QWidget(self)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._magnitude_spin = DoubleSpinBox()
        self._magnitude_spin.setRange(-_FLOAT_MAX, _FLOAT_MAX)
        self._magnitude_spin.setDecimals(6)
        self._magnitude_spin.setSingleStep(0.01)
        self._magnitude_spin.valueChanged.connect(lambda _: self._clear_error())

        self._unit_combo = ComboBox()
        self._unit_combo.setMinimumWidth(90)

        # Populate units from the ChemQuantityValidator found in metadata
        validator = self._find_validator()
        if validator is not None:
            unit_strings = units_for_dimension(validator.dimensions, ureg)
        else:
            unit_strings = []

        for u in unit_strings:
            self._unit_combo.addItem(u)

        # Store the expected dimensions for validate()
        self._expected_dims = validator.dimensions if validator is not None else None

        layout.addWidget(self._magnitude_spin, stretch=1)
        layout.addWidget(self._unit_combo)
        return container

    def _find_validator(self):
        """Return the first ChemQuantityValidator found in field_info.metadata."""
        from chemunited_core.utils import ChemQuantityValidator

        for meta in (self._field_info.metadata or []):
            if isinstance(meta, ChemQuantityValidator):
                return meta
        return None

    def get_value(self) -> ChemUnitQuantity:
        magnitude = self._magnitude_spin.value()
        unit = self._unit_combo.currentText()
        return ChemUnitQuantity(magnitude, unit)

    def set_value(self, value) -> None:
        if isinstance(value, ChemUnitQuantity):
            self._magnitude_spin.setValue(float(value.magnitude))
            unit_str = str(value.units)
            idx = self._unit_combo.findText(unit_str)
            if idx >= 0:
                self._unit_combo.setCurrentIndex(idx)
        elif value is not None:
            # Try to parse from string
            try:
                q = ChemUnitQuantity.parse(str(value))
                self.set_value(q)
            except Exception:
                pass

    def validate(self) -> bool:
        magnitude = self._magnitude_spin.value()
        if not math.isfinite(magnitude):
            self._set_error("Magnitude must be a finite number")
            return False

        unit_str = self._unit_combo.currentText()
        if not unit_str:
            self._set_error("Select a unit")
            return False

        if self._expected_dims is not None:
            try:
                q = ureg.Quantity(magnitude, unit_str)
                if q.dimensionality != self._expected_dims:
                    self._set_error("Unit dimensionality does not match the required dimension")
                    return False
            except Exception as exc:
                self._set_error(f"Invalid unit: {exc}")
                return False

        self._mark_valid()
        return True
