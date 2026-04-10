from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    CaptionLabel,
    PrimaryPushButton,
    PushButton,
)
from qframelesswindow import FramelessDialog


class _NoticeBanner(QWidget):
    """Small coloured banner shown at the top of a converted-from-command script."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            "QWidget {"
            "  background: #EEEDFE;"
            "  border-radius: 6px;"
            "  padding: 4px 10px;"
            "}"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)

        icon = QLabel("ℹ")
        icon.setStyleSheet("color: #3C3489; font-size: 13px; background: transparent;")
        layout.addWidget(icon)

        lbl = CaptionLabel(text)
        lbl.setStyleSheet("color: #3C3489; background: transparent;")
        lbl.setWordWrap(True)
        layout.addWidget(lbl, stretch=1)


class ScriptEditorDialog(FramelessDialog):
    """Script editor dialog.

    Opened either directly (double-click on a script/if block) or
    as a result of the user confirming "convert to script" inside
    ``CommandEditorDialog``.

    When opened after a conversion, the ``source`` argument contains the
    pre-filled Python code.  A notice banner is shown to remind the user
    that the original command form is no longer available.

    Layout
    ------
    ┌────────────────────────────────────┬──────────────────┐
    │  [script badge]  <block name>      │                  │  header
    ├────────────────────────────────────┤  Assistant       │
    │  [notice banner — if converted]    │  sidebar         │
    ├────────────────────────────────────┤                  │
    │                                    │  + add command   │
    │   code editor area                 │  ⇢ pathway       │
    │   (QPlainTextEdit placeholder)     │  P process param │
    │                                    │  M main param    │
    │                                    │  ─────────────── │
    │                                    │  B black fmt     │
    ├────────────────────────────────────┴──────────────────┤
    │                              [Cancel]  [Save]         │  footer
    └────────────────────────────────────────────────────────┘

    Signals
    -------
    saved(str)
        Emitted with the current script source when the user clicks Save.
    """

    saved = pyqtSignal(str)

    def __init__(
        self,
        block_name: str,
        source: str = "",
        converted_from_command: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        """
        Parameters
        ----------
        block_name
            Name of the script/if block — shown in the header.
        source
            Initial Python source to populate the editor with.
        converted_from_command
            When True a notice banner is shown at the top of the editor area
            to remind the user that form-based editing is no longer available.
        """
        super().__init__(parent)
        self._block_name = block_name
        self._source = source
        self._converted = converted_from_command

        self.setWindowTitle(f"Script — {block_name}")
        self.setMinimumSize(660, 480)
        self.setResizeEnabled(True)

        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, self.titleBar.height(), 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())
        root.addWidget(self._build_body(), stretch=1)
        root.addWidget(self._build_footer())

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setStyleSheet("border-bottom: 1px solid rgba(0,0,0,0.08);")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(8)

        badge = QLabel("script")
        badge.setStyleSheet(
            "QLabel {"
            "  background: #EEEDFE;"
            "  color: #3C3489;"
            "  border-radius: 4px;"
            "  padding: 2px 8px;"
            "  font-size: 11px;"
            "  font-weight: 600;"
            "}"
        )
        layout.addWidget(badge)

        name_lbl = QLabel(self._block_name)
        name_lbl.setStyleSheet("font-size: 13px; font-weight: 500;")
        layout.addWidget(name_lbl)
        layout.addStretch()

        return header

    def _build_body(self) -> QWidget:
        body = QWidget()
        layout = QHBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- left: notice + code editor ---
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        if self._converted:
            banner = _NoticeBanner(
                "Converted from command block — form fields no longer available"
            )
            left_layout.addWidget(banner)

        # TODO: replace QLabel placeholder with a real code editor widget
        # (e.g. QsciScintilla, or your existing script editor component)
        from PyQt5.QtWidgets import QPlainTextEdit

        self._editor = QPlainTextEdit()
        self._editor.setPlainText(self._source)
        self._editor.setStyleSheet(
            "QPlainTextEdit {"
            "  font-family: 'Courier New', monospace;"
            "  font-size: 12px;"
            "  border: none;"
            "  background: rgba(0,0,0,0.02);"
            "}"
        )
        left_layout.addWidget(self._editor, stretch=1)

        layout.addWidget(left, stretch=1)

        # --- right: assistant sidebar ---
        layout.addWidget(self._build_sidebar())

        return body

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setFixedWidth(160)
        sidebar.setStyleSheet("border-left: 1px solid rgba(0,0,0,0.08);")

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(2)

        section_lbl = CaptionLabel("ASSISTANTS")
        section_lbl.setStyleSheet(
            "color: grey; letter-spacing: 0.06em; padding: 4px 12px 6px 12px;"
        )
        layout.addWidget(section_lbl)

        def _action_btn(icon_text: str, label: str, color: str, bg: str) -> QWidget:
            btn = PushButton(f"{icon_text}  {label}")
            btn.setStyleSheet(
                f"QPushButton {{"
                f"  text-align: left;"
                f"  padding: 6px 12px;"
                f"  border: none;"
                f"  font-size: 12px;"
                f"  color: {color};"
                f"}}"
                f"QPushButton:hover {{ background: rgba(0,0,0,0.04); }}"
            )
            # TODO: connect each button to the appropriate insertion helper
            return btn

        layout.addWidget(_action_btn("+", "add command", "#185FA5", "#E6F1FB"))
        layout.addWidget(_action_btn("⇢", "pathway", "#0F6E56", "#E1F5EE"))
        layout.addWidget(_action_btn("P", "process param", "#854F0B", "#FAEEDA"))
        layout.addWidget(_action_btn("M", "main param", "#3C3489", "#EEEDFE"))

        layout.addStretch()

        rule = QWidget()
        rule.setFixedHeight(1)
        rule.setStyleSheet("background: rgba(0,0,0,0.08); margin: 0 12px;")
        layout.addWidget(rule)

        fmt_btn = PushButton("B  black format")
        fmt_btn.setStyleSheet(
            "QPushButton {"
            "  text-align: left;"
            "  padding: 6px 12px;"
            "  border: none;"
            "  font-size: 12px;"
            "  color: grey;"
            "}"
            "QPushButton:hover { background: rgba(0,0,0,0.04); }"
        )
        layout.addWidget(fmt_btn)

        return sidebar

    def _build_footer(self) -> QWidget:
        footer = QWidget()
        footer.setStyleSheet("border-top: 1px solid rgba(0,0,0,0.08);")
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(8)
        layout.addStretch()

        cancel_btn = PushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(cancel_btn)

        save_btn = PrimaryPushButton("Save")
        save_btn.clicked.connect(self._on_save)
        layout.addWidget(save_btn)

        return footer

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_save(self) -> None:
        self.saved.emit(self._editor.toPlainText())
        self.accept()

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def get_source(self) -> str:
        """Return the current content of the code editor."""
        return self._editor.toPlainText()
