from __future__ import annotations

from PyQt5.QtWidgets import QWidget
from qfluentwidgets import FlowLayout, ToggleButton

from .base_card import BaseFieldCard


class ChoiceFieldCard(BaseFieldCard):
    """Card for fields with a fixed set of options rendered as toggle chips.

    Expects `field_info.json_schema_extra["Options"]` to be a list of values.
    Set `json_schema_extra["multi"] = True` to allow multiple selections.
    """

    def _type_badge(self) -> str:
        return "choice"

    def _build_input(self) -> QWidget:
        extras = self._field_info.json_schema_extra or {}
        self._options = extras.get("Options", [])
        self._multi = bool(extras.get("multi", False))

        container = QWidget(self)
        self._flow = FlowLayout(container, needAni=False)
        self._flow.setContentsMargins(0, 0, 0, 0)
        self._flow.setHorizontalSpacing(6)
        self._flow.setVerticalSpacing(6)

        self._buttons: list[ToggleButton] = []
        for option in self._options:
            btn = ToggleButton(str(option))
            btn.toggled.connect(lambda checked, o=option: self._on_toggle(o, checked))
            self._buttons.append(btn)
            self._flow.addWidget(btn)

        return container

    def _on_toggle(self, option, checked: bool) -> None:
        if not self._multi and checked:
            # Deselect all others
            for btn, opt in zip(self._buttons, self._options):
                if opt != option and btn.isChecked():
                    btn.blockSignals(True)
                    btn.setChecked(False)
                    btn.blockSignals(False)
        self._clear_error()
        self.value_changed.emit(self.get_value())

    def get_value(self):
        selected = [
            opt for btn, opt in zip(self._buttons, self._options) if btn.isChecked()
        ]
        if self._multi:
            return selected
        return selected[0] if selected else None

    def set_value(self, value) -> None:
        if self._multi:
            selected_set = set(value) if value else set()
        else:
            selected_set = {value} if value is not None else set()

        for btn, opt in zip(self._buttons, self._options):
            btn.blockSignals(True)
            btn.setChecked(opt in selected_set)
            btn.blockSignals(False)

    def validate(self) -> bool:
        if self.get_value() is None or self.get_value() == []:
            self._set_error("At least one option must be selected")
            return False
        self._mark_valid()
        return True
