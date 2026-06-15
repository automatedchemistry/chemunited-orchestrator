from __future__ import annotations

from PyQt5.QtWidgets import QHBoxLayout, QWidget
from qfluentwidgets import SwitchButton

from .base_card import BaseFieldCard


def _extras_dict(field_info) -> dict[str, object]:
    extras = field_info.json_schema_extra
    return extras if isinstance(extras, dict) else {}


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
        self.apply_text_options(_extras_dict(self._field_info))
        self._switch.checkedChanged.connect(self._on_toggled)

        layout.addWidget(self._switch)
        layout.addStretch()
        return container

    def apply_text_options(self, extras: dict[str, object]) -> None:
        on_text = extras.get("on_text")
        off_text = extras.get("off_text")
        if on_text is not None:
            self._switch.setOnText(str(on_text))
        if off_text is not None:
            self._switch.setOffText(str(off_text))

    def _on_toggled(self, checked: bool) -> None:
        self.value_changed.emit(checked)

    def get_value(self) -> bool:
        return self._switch.isChecked()

    def set_value(self, value) -> None:
        checked = bool(value)
        self._switch.setChecked(checked)
        self._switch.setText(
            self._switch.getOnText() if checked else self._switch.getOffText()
        )

    def validate(self) -> bool:
        # A bool is always valid
        self._mark_valid()
        return True
