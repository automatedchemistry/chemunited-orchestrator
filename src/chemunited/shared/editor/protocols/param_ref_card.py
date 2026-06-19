from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QHBoxLayout, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget
from qfluentwidgets import (
    CaptionLabel,
    RoundMenu,
    Action,
    StrongBodyLabel,
    TransparentToolButton,
    PushButton,
    isDarkTheme,
    FluentIcon,
)

from chemunited.shared.widgets.base_mode_editor.cards.base_card import BaseFieldCard

QT_ALIGN_LEFT = getattr(Qt, "AlignLeft")
QT_ALIGN_VCENTER = getattr(Qt, "AlignVCenter")


class ParamRefCard(QWidget):
    """Wraps a BaseFieldCard and adds a toggle to bind the parameter to a
    self.config.X or self.main_parameters.X reference instead of a literal value.

    Exposes the same minimal interface expected by BaseModeEditorWidget.save():
      validate(), get_value(), set_value(), isHidden()

    In *literal mode* the wrapped card is visible and behaves normally.
    In *reference mode* the wrapped card is hidden and a label shows the active
    reference expression; the literal value is still returned by get_value() so
    the Pydantic model can be instantiated with a valid default.
    """

    def __init__(
        self,
        name: str,
        wrapped_card: BaseFieldCard,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._name = name
        self._wrapped = wrapped_card
        self._active_ref: str | None = None
        self._options: list[tuple[str, str]] = []

        self._setup_ui()

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Header row (title + link button) ──────────────────────────────
        header = QHBoxLayout()
        header.setContentsMargins(16, 10, 16, 4)
        header.setSpacing(6)

        self._title_label = StrongBodyLabel(
            self._wrapped._field_info.title or self._name
        )
        header.addWidget(self._title_label, alignment=QT_ALIGN_VCENTER)
        header.addStretch()

        self._ref_button = TransparentToolButton(FluentIcon.LINK, self)
        self._ref_button.setFixedSize(22, 22)
        self._ref_button.setToolTip("Bind to a process parameter reference")
        self._ref_button.setVisible(False)
        self._ref_button.clicked.connect(self._show_ref_menu)
        header.addWidget(self._ref_button, alignment=QT_ALIGN_VCENTER)

        outer.addLayout(header)

        # ── Stacked area: page 0 = wrapped card, page 1 = reference label ─
        self._stack = QStackedWidget(self)
        self._stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        # Page 0: original card (re-parented into this widget)
        self._wrapped.setParent(self._stack)
        self._stack.addWidget(self._wrapped)

        # Page 1: reference indicator
        ref_page = QWidget(self._stack)
        ref_layout = QHBoxLayout(ref_page)
        ref_layout.setContentsMargins(16, 8, 16, 10)
        ref_layout.setSpacing(8)

        self._ref_label = CaptionLabel("", ref_page)
        self._ref_label.setStyleSheet("color: #2d7dff; font-style: italic;")
        ref_layout.addWidget(self._ref_label, alignment=QT_ALIGN_VCENTER)
        ref_layout.addStretch()

        clear_btn = PushButton("clear", ref_page)
        clear_btn.setFixedWidth(60)
        clear_btn.clicked.connect(self.clear_reference)
        ref_layout.addWidget(clear_btn, alignment=QT_ALIGN_VCENTER)

        self._stack.addWidget(ref_page)

        outer.addWidget(self._stack)

    # ── Reference mode API ─────────────────────────────────────────────────────

    def enable_reference_mode(self, options: list[tuple[str, str]]) -> None:
        """Show the link button and configure the available reference options.

        options: list of (display_label, reference_expression) pairs.
        """
        self._options = options
        self._ref_button.setVisible(True)

    def set_reference(self, ref: str) -> None:
        self._active_ref = ref
        self._ref_label.setText(f"→  {ref}")
        self._stack.setCurrentIndex(1)

    def clear_reference(self) -> None:
        self._active_ref = None
        self._stack.setCurrentIndex(0)

    @property
    def active_reference(self) -> str | None:
        return self._active_ref

    # ── Menu ───────────────────────────────────────────────────────────────────

    def _show_ref_menu(self) -> None:
        menu = RoundMenu(parent=self)
        menu.addAction(
            Action(
                FluentIcon.CLOSE,
                "None (use literal value)",
                triggered=self.clear_reference,
            )
        )
        if self._options:
            menu.addSeparator()
        for label, ref in self._options:
            menu.addAction(
                Action(
                    FluentIcon.LINK,
                    label,
                    triggered=lambda _checked=False, r=ref: self.set_reference(r),
                )
            )
        btn_pos = self._ref_button.mapToGlobal(self._ref_button.rect().bottomLeft())
        menu.exec(btn_pos)

    # ── BaseModeEditorWidget-compatible interface ──────────────────────────────

    def get_value(self):
        return self._wrapped.get_value()

    def set_value(self, value) -> None:
        self._wrapped.set_value(value)

    def validate(self) -> bool:
        if self._active_ref is not None:
            return True
        return self._wrapped.validate()
