"""Card list widget for the parameters editor."""

from __future__ import annotations

import copy
from collections.abc import Callable, Iterator, Generator
from contextlib import contextmanager

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QVBoxLayout, QWidget
from qfluentwidgets import SmoothScrollArea

from chemunited.qt.shared.widgets.base_mode_editor.cards.builder_models import (
    BasicVariableBuildMode,
)

from .cards import VariableCard

QT_SCROLLBAR_ALWAYS_OFF = getattr(Qt, "ScrollBarAlwaysOff")


class ParameterListWidget(SmoothScrollArea):
    """Scrollable list of parameter cards with live-write notifications."""

    def __init__(
        self,
        class_name: str = "MainParameters",
        base_class_name: str = "BaseModel",
        write_callback: Callable[[str], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._class_name = class_name
        self._base_class_name = base_class_name
        self._write_callback = write_callback
        self._suspend_write_depth = 0

        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(QT_SCROLLBAR_ALWAYS_OFF)
        self.enableTransparentBackground()

        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(10, 10, 10, 10)
        self._layout.setSpacing(8)
        self._layout.addStretch()

        self.setWidget(self._container)
        self._cards: list[VariableCard] = []

    @contextmanager
    def suspend_writes(self) -> Generator[None, None, None]:
        """Temporarily suppress live writes while cards are populated."""
        self._suspend_write_depth += 1
        try:
            yield
        finally:
            self._suspend_write_depth -= 1

    def set_base_class_name(self, name: str) -> None:
        self._base_class_name = name

    def add_card(self, mode: BasicVariableBuildMode) -> VariableCard:
        """Append a new card and flush if writes are enabled."""
        card = VariableCard(mode, self._container)
        card.changed.connect(self._on_card_changed)
        card.deleted.connect(self._remove_card)
        card.duplicate.connect(self._duplicate_card)

        self._layout.insertWidget(self._layout.count() - 1, card)
        self._cards.append(card)
        self._flush()
        return card

    def build_source(self) -> str:
        """Return the rendered class definition or an empty string if invalid."""
        if not self._cards:
            return f"class {self._class_name}({self._base_class_name}):\n    pass\n"

        snippets: list[str] = []
        for card in self._cards:
            snippet = card.get_field_code()
            if not snippet:
                return ""
            snippets.append(snippet)

        body = "\n\n".join(snippets)
        return f"class {self._class_name}({self._base_class_name}):\n\n{body}\n"

    def validate_all(self) -> bool:
        return all(card.validate() for card in self._cards)

    def clear_all(self) -> None:
        with self.suspend_writes():
            for card in list(self._cards):
                self._remove_card(card)
        self._flush()

    def _flush(self) -> None:
        if self._suspend_write_depth or self._write_callback is None:
            return

        source = self.build_source()
        if source:
            self._write_callback(source)

    def _on_card_changed(self) -> None:
        self._flush()

    def _remove_card(self, card: VariableCard) -> None:
        self._cards.remove(card)
        self._layout.removeWidget(card)
        card.deleteLater()
        self._flush()

    def _duplicate_card(self, card: VariableCard) -> None:
        self.add_card(copy.deepcopy(card.mode))
