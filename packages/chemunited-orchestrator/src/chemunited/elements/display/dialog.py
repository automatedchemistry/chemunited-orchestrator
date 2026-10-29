"""LcdDisplayDialog — name an LCD and bind it to a device variable or custom source."""

from __future__ import annotations

import json
from collections.abc import Collection, Mapping, Sequence
from typing import Any

from pydantic import ValidationError
from PyQt5.QtWidgets import QFormLayout, QHBoxLayout, QVBoxLayout
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    ComboBox,
    LineEdit,
    PrimaryPushButton,
    PushButton,
)
from qframelesswindow import FramelessDialog

from .model import CUSTOM_COMPONENT, LcdDisplay, device_variables

MONITORED_SUFFIX = "  ● monitored"


def _same_variable(variable: Mapping[str, Any], component: str, command: str) -> bool:
    return variable.get("component") == component and variable.get("command") == command


class LcdDisplayDialog(FramelessDialog):
    """Form for an LCD: its name, device, variable, the variable's parameters and unit.

    The variables are the device's GET commands from its protocol definition,
    or, for ``custom``, the project's custom monitoring sources; the ones in
    the project's monitoring list are marked. An LCD can still be bound to one
    that isn't: the dashboard then shows "not monitored".
    """

    def __init__(
        self,
        *,
        devices: Mapping[str, str],
        monitored: Sequence[Mapping[str, Any]],
        taken_names: Collection[str],
        name: str,
        position: tuple[float, float],
        custom_sources: Collection[str] = (),
        component: str = "",
        command: str = "",
        kwargs: Mapping[str, Any] | None = None,
        unit: str = "",
        creation: bool = True,
        parent=None,
    ) -> None:
        super().__init__(parent=parent)
        self.setWindowTitle("Add LCD" if creation else "LCD Properties")
        self.setResizeEnabled(False)
        self._devices = dict(devices)  # name -> figure
        self._custom_sources = sorted(custom_sources)
        self._monitored = list(monitored)
        self._taken_names = set(taken_names)
        self._position = position
        self._variables: dict[str, dict[str, Any]] = {}
        self._result: LcdDisplay | None = None

        self.name_edit = LineEdit(self)
        self.name_edit.setText(name)
        self.device_combo = ComboBox(self)
        for device in sorted(self._devices):
            self.device_combo.addItem(device, userData=device)
        if self._custom_sources:
            # Named as on the dashboard's Monitoring page.
            self.device_combo.addItem(CUSTOM_COMPONENT, userData=CUSTOM_COMPONENT)
        self.variable_combo = ComboBox(self)
        self.params_edit = LineEdit(self)
        self.params_edit.setPlaceholderText('{"channel": "1"}')
        self.monitoring_hint = CaptionLabel("", self)
        self.monitoring_hint.setWordWrap(True)
        self.unit_edit = LineEdit(self)
        self.unit_edit.setText(unit)
        self.unit_edit.setPlaceholderText("bar, °C")
        unit_hint = CaptionLabel("Shown after the reading when it's a number.", self)

        form = QFormLayout()
        form.setSpacing(12)
        form.addRow("Name", self.name_edit)
        form.addRow("Device", self.device_combo)
        form.addRow("Variable", self.variable_combo)
        form.addRow("Parameters", self.params_edit)
        form.addRow("", self.monitoring_hint)
        form.addRow("Unit", self.unit_edit)
        form.addRow("", unit_hint)

        self.error_label = BodyLabel("", self)
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #c42b1c;")
        self.error_label.hide()

        cancel_button = PushButton("Cancel", self)
        cancel_button.clicked.connect(self.reject)  # type: ignore[attr-defined]
        save_button = PrimaryPushButton("Add LCD" if creation else "Save", self)
        save_button.clicked.connect(self._save)  # type: ignore[attr-defined]
        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(cancel_button)
        actions.addWidget(save_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, self.titleBar.height() + 20, 24, 20)
        layout.setSpacing(14)
        layout.addWidget(
            CaptionLabel(
                "The dashboard shows this variable's latest monitoring reading "
                "on the LCD while the platform view is live.",
                self,
            )
        )
        layout.addLayout(form)
        layout.addWidget(self.error_label)
        layout.addLayout(actions)
        self.setMinimumWidth(520)

        index = self.device_combo.findData(component)
        if index >= 0:
            self.device_combo.setCurrentIndex(index)
        self._load_variables(select=command, params=kwargs)
        self.device_combo.currentIndexChanged.connect(  # type: ignore[attr-defined]
            lambda _: self._load_variables()
        )
        self.variable_combo.currentIndexChanged.connect(  # type: ignore[attr-defined]
            lambda _: self._show_defaults()
        )
        self.params_edit.textChanged.connect(  # type: ignore[attr-defined]
            lambda _: self._update_monitoring_hint()
        )

    # ── variables ───────────────────────────────────────────────────────────

    def _component(self) -> str:
        return str(self.device_combo.currentData() or "")

    def _custom_defaults(self, source: str) -> dict[str, Any]:
        """The parameters of *source*'s first entry in the monitoring list.

        Never guessed from the function: other parameters would make another
        variable than the one monitored.
        """
        for variable in self._monitored:
            if _same_variable(variable, CUSTOM_COMPONENT, source):
                return dict(variable.get("kwargs") or {})
        return {}

    def _load_variables(
        self, select: str = "", params: Mapping[str, Any] | None = None
    ) -> None:
        component = self._component()
        if component == CUSTOM_COMPONENT:
            self._variables = {
                source: self._custom_defaults(source) for source in self._custom_sources
            }
        else:
            figure = self._devices.get(component)
            try:
                self._variables = device_variables(figure, component) if figure else {}
            except Exception:
                self._variables = {}
        self.variable_combo.blockSignals(True)
        self.variable_combo.clear()
        for command in sorted(self._variables):
            monitored = any(
                _same_variable(variable, component, command)
                for variable in self._monitored
            )
            self.variable_combo.addItem(
                command + (MONITORED_SUFFIX if monitored else ""), userData=command
            )
        commands = sorted(self._variables)
        if select in commands:
            self.variable_combo.setCurrentIndex(commands.index(select))
        self.variable_combo.blockSignals(False)
        if params is not None and select in commands:
            self.params_edit.setText(json.dumps(dict(params)) if params else "")
            self._update_monitoring_hint()
        else:
            self._show_defaults()

    def _show_defaults(self) -> None:
        defaults = self._variables.get(self._command(), {})
        self.params_edit.setText(json.dumps(defaults) if defaults else "")
        self._update_monitoring_hint()

    def _command(self) -> str:
        return str(self.variable_combo.currentData() or "")

    def _params(self) -> dict[str, Any]:
        text = self.params_edit.text().strip()
        if not text:
            return {}
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise ValueError('Parameters must be a JSON object, like {"channel": "1"}.')
        return parsed

    def _update_monitoring_hint(self) -> None:
        component, command = self._component(), self._command()
        try:
            params = self._params()
        except ValueError:
            self.monitoring_hint.setText("")
            return
        monitored = any(
            _same_variable(variable, component, command)
            and (variable.get("kwargs") or {}) == params
            for variable in self._monitored
        )
        self.monitoring_hint.setText(
            "In the monitoring list."
            if monitored
            else 'Not in the monitoring list: the LCD will show "not monitored" '
            "until it's added on the dashboard's Monitoring page."
        )

    # ── result ──────────────────────────────────────────────────────────────

    def _fail(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.show()

    def _save(self) -> None:
        name = self.name_edit.text().strip()
        if name in self._taken_names:
            self._fail(f"Another LCD is already called '{name}'.")
            return
        if not self._command():
            self._fail("Pick a device or custom source with a variable to show.")
            return
        try:
            params = self._params()
        except ValueError as exc:
            self._fail(f"Parameters: {exc}")
            return
        try:
            self._result = LcdDisplay(
                name=name,
                position=self._position,
                component=self._component(),
                command=self._command(),
                kwargs=params,
                unit=self.unit_edit.text(),
            )
        except ValidationError as exc:
            error = exc.errors()[0]
            field = ".".join(str(part) for part in error.get("loc", ()))
            self._fail(f"{field.capitalize()}: {error.get('msg', 'invalid value')}")
            return
        self.accept()

    def get_result_instance(self) -> LcdDisplay | None:
        return self._result
