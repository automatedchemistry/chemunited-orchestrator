from __future__ import annotations

from pathlib import Path
from typing import Mapping

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    DoubleSpinBox,
    PrimaryPushButton,
    PushButton,
    StrongBodyLabel,
    SwitchButton,
    isDarkTheme,
)
from qframelesswindow import FramelessDialog

from chemunited_core.protocols import CommandSignature
from chemunited.shared.editor.base import EditorBase
from chemunited.shared.widgets.base_mode_editor import BaseModeEditorWidget

QT_ALIGN_LEFT = getattr(Qt, "AlignLeft")
QT_ALIGN_RIGHT = getattr(Qt, "AlignRight")


class _ConfirmConvertDialog(FramelessDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.setWindowTitle("Convert to Script")
        self.setResizeEnabled(False)
        self.setFixedWidth(420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, self.titleBar.height() + 16, 24, 20)
        layout.setSpacing(12)

        title = StrongBodyLabel(
            "Convert this block to a custom script block?",
            self,
        )
        title.setWordWrap(True)
        layout.addWidget(title)

        message = BodyLabel(
            "If you proceed, this block will become a custom script block forever. "
            "You will no longer be able to edit it with the command form.",
            self,
        )
        message.setWordWrap(True)
        layout.addWidget(message)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 4, 0, 0)
        actions.addStretch()

        cancel_button = PushButton("cancel", self)
        cancel_button.clicked.connect(self.reject)
        actions.addWidget(cancel_button)

        confirm_button = PrimaryPushButton("convert", self)
        confirm_button.clicked.connect(self.accept)
        actions.addWidget(confirm_button)

        layout.addLayout(actions)


class CommandEditorDialog(FramelessDialog):
    saved = pyqtSignal(object)
    convert_to_script = pyqtSignal(str)

    def __init__(
        self,
        file_path: Path,
        function_name: str,
        command_model: CommandSignature,
        parent=None,
    ):
        super().__init__(parent)

        self._file_path = file_path
        self._function_name = function_name
        self._command_model = command_model
        self._result_instance: CommandSignature | None = None

        self._code_preview_widget = EditorBase(parent=self, path=file_path)
        self._code_preview_widget.setReadOnly(True)
        self._code_preview_widget.set_autosave(False)

        base_fields = set(CommandSignature.model_fields)
        field_overrides: dict[str, Mapping[str, object]] = {
            name: {"visible": False, "editable": False} for name in base_fields
        }
        self._editor = BaseModeEditorWidget(
            model_class=type(command_model),
            instance=command_model,
            field_overrides=field_overrides,
            parent=self,
        )
        self._strip_editor_footer()

        self._custom_wait_switch = SwitchButton(self)
        self._feedback_switch = SwitchButton(self)
        self._custom_wait_spin = DoubleSpinBox(self)
        self._custom_wait_container = QWidget(self)

        self.setObjectName("commandEditorDialog")
        self.setWindowTitle(function_name or "Command editor")
        self.setMinimumSize(760, 680)
        self.resize(860, 720)
        self._build_ui()
        self._apply_styles()
        self._bind_preview_updates()
        self._update_preview()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, self.titleBar.height() + 16, 16, 16)
        layout.setSpacing(12)

        layout.addLayout(self._build_header())
        layout.addWidget(self._make_separator())
        layout.addWidget(self._editor, stretch=1)
        layout.addWidget(self._build_execution_control())
        layout.addWidget(self._build_preview_section(), stretch=1)
        layout.addLayout(self._build_footer())

    def _build_header(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        tag_row = QHBoxLayout()
        tag_row.setContentsMargins(0, 0, 0, 0)
        tag_row.setSpacing(8)

        kind_tag = QLabel("command", self)
        kind_tag.setObjectName("commandKindTag")
        tag_row.addWidget(kind_tag, alignment=QT_ALIGN_LEFT)

        command_tag = QLabel(self._header_summary, self)
        command_tag.setObjectName("commandSummaryTag")
        tag_row.addWidget(command_tag, alignment=QT_ALIGN_LEFT)

        tag_container = QWidget(self)
        tag_container.setLayout(tag_row)
        layout.addWidget(tag_container, stretch=1, alignment=QT_ALIGN_LEFT)

        self._convert_button = PushButton("convert to script", self)
        self._convert_button.clicked.connect(self._on_convert_to_script)
        layout.addWidget(self._convert_button, alignment=QT_ALIGN_RIGHT)

        return layout

    def _build_execution_control(self) -> QWidget:
        section = QWidget(self)
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        caption = CaptionLabel("EXECUTION CONTROL", section)
        caption.setObjectName("sectionCaption")
        layout.addWidget(caption)

        custom_wait_enabled = self._command_model.wait_time > 0

        self._custom_wait_switch.setChecked(custom_wait_enabled)
        layout.addWidget(
            self._build_switch_row(
                title="Custom wait after",
                switch=self._custom_wait_switch,
                parent=section,
            )
        )

        wait_container_layout = QVBoxLayout(self._custom_wait_container)
        wait_container_layout.setContentsMargins(0, 0, 0, 0)
        wait_container_layout.setSpacing(4)

        self._custom_wait_spin.setRange(0.0, 86400.0)
        self._custom_wait_spin.setDecimals(2)
        self._custom_wait_spin.setSingleStep(0.5)
        self._custom_wait_spin.setSuffix(" s")
        self._custom_wait_spin.setValue(max(0.0, float(self._command_model.wait_time)))
        wait_container_layout.addWidget(self._custom_wait_spin)
        self._custom_wait_container.setVisible(custom_wait_enabled)
        layout.addWidget(self._custom_wait_container)

        self._feedback_switch.setChecked(
            bool(getattr(self._command_model, "wait_feedback_status", False))
        )
        layout.addWidget(
            self._build_switch_row(
                title="Wait for device feedback",
                switch=self._feedback_switch,
                parent=section,
            )
        )

        self._custom_wait_switch.checkedChanged.connect(
            self._custom_wait_container.setVisible
        )

        return section

    def _build_switch_row(
        self,
        title: str,
        switch: SwitchButton,
        parent: QWidget,
    ) -> QWidget:
        row = QWidget(parent)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        label = BodyLabel(title, row)
        label.setObjectName("controlLabel")
        layout.addWidget(label)
        layout.addStretch()
        layout.addWidget(switch, alignment=QT_ALIGN_RIGHT)
        return row

    def _build_preview_section(self) -> QWidget:
        section = QWidget(self)
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        preview_header = QWidget(section)
        preview_header.setObjectName("previewHeader")
        preview_header_layout = QHBoxLayout(preview_header)
        preview_header_layout.setContentsMargins(12, 8, 12, 8)
        preview_header_layout.setSpacing(8)

        indicator = QLabel("o", preview_header)
        indicator.setObjectName("previewIndicator")
        preview_header_layout.addWidget(indicator)

        title = StrongBodyLabel("LIVE CODE PREVIEW", preview_header)
        title.setObjectName("previewLabel")
        preview_header_layout.addWidget(title)
        preview_header_layout.addStretch()

        layout.addWidget(preview_header)
        self._code_preview_widget.setMinimumHeight(200)
        layout.addWidget(self._code_preview_widget, stretch=1)
        return section

    def _build_footer(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addStretch()

        cancel_button = PushButton("cancel", self)
        cancel_button.setMinimumWidth(92)
        cancel_button.clicked.connect(self.reject)
        layout.addWidget(cancel_button)

        save_button = PrimaryPushButton("save", self)
        save_button.setMinimumWidth(92)
        save_button.clicked.connect(self._on_save)
        layout.addWidget(save_button)

        return layout

    def _apply_styles(self) -> None:
        panel_border = (
            "rgba(255, 255, 255, 0.12)" if isDarkTheme() else "rgba(0, 0, 0, 0.12)"
        )
        panel_fill = (
            "rgba(255, 255, 255, 0.03)" if isDarkTheme() else "rgba(0, 0, 0, 0.03)"
        )
        dialog_fill = "#2f2f2f" if isDarkTheme() else "#f7f7f7"
        section_color = (
            "rgba(255, 255, 255, 0.65)" if isDarkTheme() else "rgba(0, 0, 0, 0.55)"
        )

        self.setStyleSheet(
            f"""
            QDialog#commandEditorDialog {{
                background-color: {dialog_fill};
                border: 1px solid {panel_border};
                border-radius: 10px;
            }}

            QLabel#commandKindTag {{
                background: rgba(58, 127, 219, 0.18);
                border-radius: 6px;
                color: #2d7dff;
                font-weight: 600;
                padding: 4px 10px;
            }}

            QLabel#commandSummaryTag {{
                background: {panel_fill};
                border: 1px solid {panel_border};
                border-radius: 6px;
                padding: 4px 10px;
            }}

            QLabel#sectionCaption {{
                color: {section_color};
                font-weight: 700;
                letter-spacing: 0.08em;
            }}

            QLabel#controlLabel {{
                font-weight: 600;
            }}

            QWidget#previewHeader {{
                background: {panel_fill};
                border: 1px solid {panel_border};
                border-bottom: none;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
            }}

            QLabel#previewIndicator {{
                color: #4aa543;
                font-weight: 700;
            }}
            """
        )

    def _make_separator(self) -> QFrame:
        line = QFrame(self)
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Plain)
        line.setStyleSheet(
            "color: rgba(255, 255, 255, 0.12);"
            if isDarkTheme()
            else "color: rgba(0, 0, 0, 0.12);"
        )
        return line

    def _strip_editor_footer(self) -> None:
        layout = self._editor.layout()
        if layout is None or layout.count() < 2:
            return

        footer_item = layout.takeAt(layout.count() - 1)
        if footer_item is None:
            return
        footer_layout = footer_item.layout()
        if footer_layout is None:
            return

        while footer_layout.count():
            child = footer_layout.takeAt(0)
            if child is None:
                continue
            widget = child.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)

        footer_layout.deleteLater()

    def _bind_preview_updates(self) -> None:
        self._connect_widget_signals(self._editor)
        self._connect_widget_signals(self._custom_wait_container)
        self._feedback_switch.checkedChanged.connect(self._update_preview)
        self._custom_wait_switch.checkedChanged.connect(self._update_preview)

    def _connect_widget_signals(self, root: QWidget) -> None:
        signal_names = (
            "valueChanged",
            "textChanged",
            "currentTextChanged",
            "checkedChanged",
            "toggled",
        )

        for widget in root.findChildren(QWidget):
            for name in signal_names:
                signal = getattr(widget, name, None)
                if signal is None:
                    continue
                try:
                    signal.connect(self._update_preview)
                except Exception:
                    continue

    @property
    def _header_summary(self) -> str:
        command = self._command_model.command or self._function_name
        return f"{self._command_model.component} | {self._command_model.method} | {command}"

    def _base_instance(self) -> CommandSignature | None:
        captured: dict[str, CommandSignature] = {}

        def _store(instance: CommandSignature) -> None:
            captured["instance"] = instance

        self._editor.saved.connect(_store)
        try:
            self._editor.save()
        finally:
            self._editor.saved.disconnect(_store)

        instance = captured.get("instance")
        if instance is None:
            return None

        instance.wait_time = (
            float(self._custom_wait_spin.value())
            if self._custom_wait_switch.isChecked()
            else 0.0
        )
        instance.wait_feedback_status = self._feedback_switch.isChecked()
        return instance

    def _current_argument_values(self) -> dict[str, object]:
        values: dict[str, object] = {}
        for name, card in self._editor._cards.items():
            if name in CommandSignature.model_fields or card.isHidden():
                continue
            values[name] = card.get_value()

        if self._custom_wait_switch.isChecked():
            values["wait_time"] = float(self._custom_wait_spin.value())
        if self._feedback_switch.isChecked():
            values["wait_feedback_status"] = True

        return values

    def _format_argument(self, value: object) -> str:
        if hasattr(value, "magnitude") and hasattr(value, "units"):
            return f'"{value}"'
        return repr(value)

    def _build_command_source(self) -> str:
        component = self._command_model.component or self._function_name
        method = self._command_model.method.lower()
        command = self._command_model.command or self._function_name
        arguments = self._current_argument_values()

        if not arguments:
            return f"platform[{component!r}].{method}({command!r})"

        lines = [
            f"platform[{component!r}].{method}(",
            f"        {command!r},",
        ]
        for name, value in arguments.items():
            lines.append(f"        {name}={self._format_argument(value)},")
        lines.append(")")
        return "\n".join(lines)

    def _build_script_source(self) -> str:
        return self._build_command_source()

    def _update_preview(self, *_args) -> None:
        self._code_preview_widget.setText(self._build_command_source())

    def _on_save(self) -> None:
        instance = self._base_instance()
        if instance is None:
            return

        self._result_instance = instance
        self.saved.emit(instance)
        self.accept()

    def _on_convert_to_script(self) -> None:
        confirm_dialog = _ConfirmConvertDialog(self)
        if confirm_dialog.exec_() != QDialog.Accepted:
            return

        instance = self._base_instance()
        if instance is None:
            return

        self._result_instance = instance
        self.convert_to_script.emit(self._build_script_source())
        self.accept()

    def get_result_instance(self) -> CommandSignature | None:
        return self._result_instance

    def get_source(self) -> str:
        return self._build_script_source()


if __name__ == "__main__":
    import sys

    from chemunited_core.utils.internal_quantity import ChemUnitQuantity
    from PyQt5.QtWidgets import QApplication, QDialog

    from chemunited_core.protocols.pumps import WithdrawParameter

    app = QApplication(sys.argv)

    command = WithdrawParameter(
        component="Pump",
        rate=ChemUnitQuantity("10 ml / min"),
        volume=ChemUnitQuantity("5 ml"),
        wait_feedback_status=True,
    )
    command.wait_time = 0.0

    dialog = CommandEditorDialog(
        file_path=Path(__file__),
        function_name="withdraw",
        command_model=command,
    )
    dialog.convert_to_script.connect(print)
    dialog.saved.connect(print)

    if dialog.exec_() == QDialog.Accepted:
        print(dialog.get_source())

    sys.exit(0)
