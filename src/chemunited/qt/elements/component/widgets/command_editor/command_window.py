from __future__ import annotations

from typing import TYPE_CHECKING, Type

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    PrimaryPushButton,
    PushButton,
    TitleLabel,
    TransparentPushButton,
)
from qframelesswindow import FramelessDialog

from chemunited.qt.elements.component.protocols.models import CommandSignature
from chemunited.qt.shared.widgets.base_mode_editor import BaseModeEditorWidget

if TYPE_CHECKING:
    pass


class _HeaderWidget(QWidget):
    """Read-only header row: [command badge]  [Device · METHOD · command]  [convert →]"""

    convert_requested = pyqtSignal()

    def __init__(
        self,
        command: Type[CommandSignature],
        instance: CommandSignature,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # --- type badge ---
        badge = QLabel("command")
        badge.setStyleSheet(
            "QLabel {"
            "  background: #E6F1FB;"
            "  color: #185FA5;"
            "  border-radius: 4px;"
            "  padding: 2px 8px;"
            "  font-size: 11px;"
            "  font-weight: 600;"
            "}"
        )
        badge.setSizePolicy(
            badge.sizePolicy().horizontalPolicy(), badge.sizePolicy().verticalPolicy()
        )
        layout.addWidget(badge)

        # --- device · method · command (read-only label) ---
        device_lbl = QLabel(
            f"{instance.component}  ·  {instance.method}  ·  {instance.command}"
        )
        device_lbl.setStyleSheet(
            "QLabel {"
            "  background: transparent;"
            "  color: grey;"
            "  font-size: 11px;"
            "  padding: 2px 8px;"
            "  border: 0.5px solid rgba(0,0,0,0.15);"
            "  border-radius: 4px;"
            "}"
        )
        layout.addWidget(device_lbl)

        layout.addStretch()

        # --- convert to script button ---
        convert_btn = TransparentPushButton("⊕  convert to script")
        convert_btn.setStyleSheet("font-size: 11px; color: grey;")
        convert_btn.clicked.connect(self.convert_requested)
        layout.addWidget(convert_btn)


class _ConfirmConvertDialog(FramelessDialog):
    """Small confirmation dialog shown before converting a command block to a script."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(340)
        self.setResizeEnabled(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, self.titleBar.height() + 16, 24, 20)
        layout.setSpacing(12)

        title = TitleLabel("Convert to script?")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        body = BodyLabel(
            "The command will be pre-filled as a script block.\n\n"
            "This cannot be undone — the parameter form will no longer be available."
        )
        body.setAlignment(Qt.AlignCenter)
        body.setWordWrap(True)
        layout.addWidget(body)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()

        cancel_btn = PushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        confirm_btn = PrimaryPushButton("Convert")
        confirm_btn.clicked.connect(self.accept)
        btn_row.addWidget(confirm_btn)

        layout.addLayout(btn_row)


class CommandEditorDialog(FramelessDialog):
    """Editor dialog opened when the user double-clicks a command block.

    Layout
    ------
    ┌──────────────────────────────────────────────────────────┐
    │  [command]  Pump · PUT · withdraw    [convert to script] │  ← _HeaderWidget
    ├──────────────────────────────────────────────────────────┤
    │  description (italic, read-only)                         │
    ├──────────────────────────────────────────────────────────┤
    │  BaseModeEditorWidget                                     │  ← parameter cards
    │  (auto-rendered from CommandSignature fields)            │  + execution control
    │                                          [Cancel] [Save] │
    └──────────────────────────────────────────────────────────┘

    Signals
    -------
    saved(CommandSignature)
        Emitted when the user clicks Save with a valid instance.

    convert_to_script(str)
        Emitted when the user confirms the convert-to-script action.
        Carries the pre-filled Python source string. The dialog closes itself.
    """

    saved = pyqtSignal(object)  # CommandSignature instance
    convert_to_script = pyqtSignal(str)  # pre-filled Python source

    def __init__(
        self,
        command_class: Type[CommandSignature],
        instance: CommandSignature | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """
        Parameters
        ----------
        command_class
            The ``CommandSignature`` subclass whose fields are rendered as cards.
        instance
            Existing instance to pre-populate the form. If None, a default
            instance is created from ``command_class`` defaults.
        """
        super().__init__(parent)
        self._command_class = command_class

        # Build a default instance if none supplied, injecting component from
        # the class-level attribute (already set at protocol registration time).
        self._instance: CommandSignature = instance or command_class.model_construct()

        self.setWindowTitle(f"{self._instance.component} · {self._instance.command}")
        self.setMinimumWidth(460)
        self.setResizeEnabled(True)

        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, self.titleBar.height() + 8, 16, 0)
        root.setSpacing(0)

        # header
        header = _HeaderWidget(self._command_class, self._instance, self)
        header.convert_requested.connect(self._on_convert_requested)
        root.addWidget(header)

        # horizontal rule
        rule = QWidget()
        rule.setFixedHeight(1)
        rule.setStyleSheet("background: rgba(0,0,0,0.08);")
        root.addWidget(rule)

        # description
        if self._instance.description:
            desc = CaptionLabel(self._instance.description)
            desc.setWordWrap(True)
            desc.setStyleSheet("color: grey; font-style: italic; padding: 8px 0 4px 0;")
            root.addWidget(desc)

        # parameter editor — BaseModeEditorWidget introspects CommandSignature
        # and renders a card for every user-facing field automatically.
        self._editor = BaseModeEditorWidget(
            model_class=self._command_class,
            instance=self._instance,
            parent=self,
        )
        self._editor.saved.connect(self._on_saved)
        self._editor.cancelled.connect(self.reject)
        root.addWidget(self._editor, stretch=1)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_saved(self, instance: CommandSignature) -> None:
        self.saved.emit(instance)
        self.accept()

    def _on_convert_requested(self) -> None:
        dlg = _ConfirmConvertDialog(self)
        if dlg.exec_() == FramelessDialog.Accepted:
            source = self._build_script_source()
            self.convert_to_script.emit(source)
            self.accept()

    # ------------------------------------------------------------------
    # Code generation
    # ------------------------------------------------------------------

    def _build_script_source(self) -> str:
        """Return the Python source that the command currently represents."""
        # Collect current field values from the editor cards
        values: dict[str, object] = {}
        for name, card in self._editor._cards.items():
            values[name] = card.get_value()

        lines = [f'platform["{self._instance.component}"].put(']
        lines.append(f'    "{self._instance.command}",')

        base_keys = set(CommandSignature.model_fields)
        for name, value in values.items():
            if name in base_keys:
                continue
            lines.append(f"    {name}={value!r},")

        wait = values.get("wait_time", self._instance.wait_time)
        if wait:
            lines.append(f"    wait={wait!r},")

        fb = values.get("wait_feedback_status", self._instance.wait_feedback_status)
        lines.append(f"    wait_feedback_status={fb},")
        lines.append(")")

        body = "\n".join("    " + ln for ln in lines)
        return (
            "def script(\n"
            '    platform: "PersonalOrchestrator",\n'
            '    process_parameters: "ProcessParameters",\n'
            '    parameters: "MainParameters",\n'
            "):\n"
            f"{body}\n"
        )
