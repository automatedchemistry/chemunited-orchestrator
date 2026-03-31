from __future__ import annotations

from PyQt5.QtWidgets import QHBoxLayout, QWidget
from qfluentwidgets import CaptionLabel, SwitchButton

from .base_card import BaseFieldCard


class BoolFieldCard(BaseFieldCard):
    """Card for `bool` fields. Uses a Fluent toggle switch."""

    def _type_badge(self) -> str:
        return "bool"

    def _build_input(self) -> QWidget:
        container = QWidget(self)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._switch = SwitchButton()
        self._state_label = CaptionLabel("Off")
        self._switch.checkedChanged.connect(self._on_toggled)

        layout.addWidget(self._switch)
        layout.addWidget(self._state_label)
        layout.addStretch()
        return container

    def _on_toggled(self, checked: bool) -> None:
        self._state_label.setText("On" if checked else "Off")
        self.value_changed.emit(checked)

    def get_value(self) -> bool:
        return self._switch.isChecked()

    def set_value(self, value) -> None:
        self._switch.setChecked(bool(value))
        self._state_label.setText("On" if value else "Off")

    def validate(self) -> bool:
        # A bool is always valid
        self._mark_valid()
        return True
