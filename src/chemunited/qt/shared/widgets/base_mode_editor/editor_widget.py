from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from pydantic import BaseModel, ValidationError
from qfluentwidgets import (
    CaptionLabel,
    PrimaryPushButton,
    PushButton,
    SmoothScrollArea,
    isDarkTheme,
)

from .card_factory import CardFactory
from .cards.base_card import BaseFieldCard


class _GroupSeparator(QWidget):
    """A labelled horizontal rule that visually separates field groups."""

    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedHeight(32)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        label = CaptionLabel(title.upper())
        label.setStyleSheet("letter-spacing: 0.08em; color: grey;")
        layout.addWidget(label)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        color = (
            QColor(255, 255, 255, 30) if isDarkTheme() else QColor(0, 0, 0, 25)
        )
        painter.setPen(color)
        mid_y = self.height() // 2
        painter.drawLine(0, mid_y, self.width(), mid_y)


class BaseModeEditorWidget(QWidget):
    """Introspects a Pydantic ``BaseModel`` and renders one typed card per field.

    Emits ``saved`` with the patched model instance when the user presses Save,
    or ``cancelled`` when the user presses Cancel.

    Usage::

        widget = BaseModeEditorWidget(MyModel, instance=existing)
        widget.saved.connect(on_save)
        widget.cancelled.connect(on_cancel)
    """

    saved = pyqtSignal(object)    # emits the updated BaseModel instance
    cancelled = pyqtSignal()

    def __init__(
        self,
        model_class: type[BaseModel],
        instance: BaseModel | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._model_class = model_class
        self._instance = instance
        self._cards: dict[str, BaseFieldCard] = {}
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Scroll area — must have self as parent so it is never a top-level window
        scroll = SmoothScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.enableTransparentBackground()

        scroll_content = QWidget(scroll)
        cards_layout = QVBoxLayout(scroll_content)
        cards_layout.setContentsMargins(16, 16, 16, 16)
        cards_layout.setSpacing(8)
        cards_layout.setAlignment(Qt.AlignTop)

        self._populate_cards(cards_layout)

        scroll.setWidget(scroll_content)
        outer.addWidget(scroll)

        # Footer (Cancel / Save)
        footer = QHBoxLayout()
        footer.setContentsMargins(16, 12, 16, 12)
        footer.addStretch()

        cancel_btn = PushButton("Cancel")
        cancel_btn.clicked.connect(self.cancel)
        footer.addWidget(cancel_btn)

        save_btn = PrimaryPushButton("Save")
        save_btn.clicked.connect(self.save)
        footer.addWidget(save_btn)

        outer.addLayout(footer)

    def _populate_cards(self, layout: QVBoxLayout) -> None:
        fields = self._model_class.model_fields
        if not fields:
            return

        # Collect unique groups preserving insertion order
        groups: list[str] = []
        by_group: dict[str, list[str]] = {}
        for name, field_info in fields.items():
            extras = field_info.json_schema_extra or {}
            group = extras.get("group", "")
            if group not in by_group:
                groups.append(group)
                by_group[group] = []
            by_group[group].append(name)

        # scroll_content is the layout's parent — use it so cards are never top-level
        scroll_content = layout.parentWidget()

        for group in groups:
            if group:
                layout.addWidget(_GroupSeparator(group, scroll_content))
            for name in by_group[group]:
                field_info = fields[name]
                card = CardFactory.build(name, field_info, scroll_content)
                if self._instance is not None:
                    value = getattr(self._instance, name, None)
                    if value is not None:
                        card.set_value(value)
                self._cards[name] = card
                layout.addWidget(card)

    # ------------------------------------------------------------------
    # Save / Cancel
    # ------------------------------------------------------------------

    def save(self) -> None:
        errors: list[str] = []
        values: dict = {}

        for name, card in self._cards.items():
            if not card.isVisible():
                continue
            if not card.validate():
                errors.append(name)
            else:
                values[name] = card.get_value()

        if errors:
            return  # card-level errors already shown; do not proceed

        try:
            instance = self._model_class(**values)
        except ValidationError as exc:
            for error in exc.errors():
                loc = error.get("loc", ())
                field = loc[0] if loc else None
                if field and field in self._cards:
                    self._cards[str(field)]._set_error(error["msg"])
            return

        self.saved.emit(instance)

    def cancel(self) -> None:
        for name, card in self._cards.items():
            card._clear_error()
            if self._instance is not None:
                value = getattr(self._instance, name, None)
                if value is not None:
                    card.set_value(value)
        self.cancelled.emit()
