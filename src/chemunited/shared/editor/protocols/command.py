from __future__ import annotations

from typing import Mapping

from chemunited_core.protocols import CommandSignature
from PyQt5.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget
from qfluentwidgets import PrimaryPushButton, PushButton, SmoothScrollArea, isDarkTheme
from qframelesswindow import FramelessDialog

from chemunited.shared.editor.protocols.node_metadata import NodeMetadataEditor
from chemunited.shared.editor.protocols.param_ref_card import ParamRefCard
from chemunited.shared.widgets.base_mode_editor import BaseModeEditorWidget

QT_ALIGN_LEFT = getattr(Qt, "AlignLeft")

_HIDDEN_COMMAND_FIELDS = {
    "component",
    "command",
    "method",
    "description",
    "id",
    "param_refs",
}


class CommandEditorDialog(FramelessDialog):
    saved = pyqtSignal(object)
    metadata_saved = pyqtSignal(str, str, str)

    def __init__(
        self,
        function_name: str,
        command_model: CommandSignature,
        label: str = "",
        description: str = "",
        config_fields: list[str] | None = None,
        main_params_fields: list[str] | None = None,
        parent=None,
    ):
        super().__init__(parent)

        self._function_name = function_name
        self._command_model = command_model
        self._result_instance: CommandSignature | None = None
        self.node_metadata_editor = NodeMetadataEditor(self)
        self.node_metadata_editor.set_values(label, description)

        field_overrides: dict[str, Mapping[str, object]] = {
            name: {"visible": False, "editable": False}
            for name in _HIDDEN_COMMAND_FIELDS
            if name in CommandSignature.model_fields
        }
        self._editor = BaseModeEditorWidget(
            model_class=type(command_model),
            instance=command_model,
            field_overrides=field_overrides,
            parent=self,
        )
        self._strip_editor_footer()
        self._setup_param_refs(command_model, config_fields or [], main_params_fields or [])
        self.custom_signal()

        self.setObjectName("commandEditorDialog")
        self.setWindowTitle(function_name or "Command editor")
        self.setMinimumSize(720, 480)
        self.resize(780, 560)
        self._build_ui()
        self._apply_styles()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, self.titleBar.height() + 16, 16, 16)
        layout.setSpacing(12)

        layout.addLayout(self._build_header())
        layout.addWidget(self._make_separator())
        layout.addWidget(self._editor, stretch=1)
        layout.addWidget(self.node_metadata_editor)
        layout.addLayout(self._build_footer())

    def _setup_param_refs(
        self,
        command_model: CommandSignature,
        config_fields: list[str],
        main_params_fields: list[str],
    ) -> None:
        if not config_fields and not main_params_fields:
            return

        options: list[tuple[str, str]] = [
            (f"self.config.{f}", f"self.config.{f}") for f in config_fields
        ] + [
            (f"self.main_parameters.{f}", f"self.main_parameters.{f}")
            for f in main_params_fields
        ]

        base_fields = set(CommandSignature.model_fields)

        scroll_area = self._editor.layout().itemAt(0).widget()
        if not isinstance(scroll_area, SmoothScrollArea):
            return
        scroll_content = scroll_area.widget()
        cards_layout = scroll_content.layout()

        for name, card in list(self._editor.cards.items()):
            if name in base_fields or card.isHidden():
                continue
            idx = cards_layout.indexOf(card)
            cards_layout.removeWidget(card)
            ref_card = ParamRefCard(name=name, wrapped_card=card, parent=scroll_content)
            ref_card.enable_reference_mode(options)
            cards_layout.insertWidget(idx, ref_card)
            self._editor.cards[name] = ref_card

        for name, ref in (command_model.param_refs or {}).items():
            if name in self._editor.cards:
                self._editor.cards[name].set_reference(ref)

    def custom_signal(self) -> None:
        cards = self._editor.cards
        cards["wait_feedback_status"].value_changed.connect(self._trigger_feedback_signal)
    
    @pyqtSlot()
    def _trigger_feedback_signal(self):
        value = self._editor.cards["wait_feedback_status"].get_value()
        self._editor.cards["feedback_status_command"].setEnabled(value)
        self._editor.cards["feedback_answer"].setEnabled(value)
    
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

        return layout

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

    @property
    def _header_summary(self) -> str:
        command = self._command_model.command or self._function_name
        return (
            f"{self._command_model.component} | "
            f"{self._command_model.method} | {command}"
        )

    def _base_instance(self) -> CommandSignature | None:
        captured: dict[str, CommandSignature] = {}

        def _store(instance: CommandSignature) -> None:
            captured["instance"] = instance

        self._editor.saved.connect(_store)
        try:
            self._editor.save()
        finally:
            self._editor.saved.disconnect(_store)

        return captured.get("instance")

    def _on_save(self) -> None:
        instance = self._base_instance()
        if instance is None:
            return

        param_refs = {
            name: card.active_reference
            for name, card in self._editor.cards.items()
            if getattr(card, "active_reference", None) is not None
        }
        instance = instance.model_copy(update={"param_refs": param_refs})

        self._result_instance = instance
        label, description = self.node_metadata_editor.values()
        self.metadata_saved.emit(self._function_name, label, description)
        self.saved.emit(instance)
        self.accept()

    def get_result_instance(self) -> CommandSignature | None:
        return self._result_instance


if __name__ == "__main__":
    import sys

    from chemunited_core.protocols.pumps import WithdrawParameter
    from chemunited_core.protocols.technical import SetTemperatureParameter
    from chemunited_quantities import ChemUnitQuantity
    from PyQt5.QtWidgets import QApplication, QDialog

    app = QApplication(sys.argv)

    command = SetTemperatureParameter(
        component="Pump",
        temp="10 degC",
        wait_feedback_status=True,
    )
    command.wait_time = 0.0

    dialog = CommandEditorDialog(
        function_name="withdraw",
        command_model=command,
    )
    dialog.saved.connect(print)

    if dialog.exec_() == QDialog.Accepted:
        print(dialog.get_result_instance())

    sys.exit(0)
