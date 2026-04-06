"""
list.py
=======
ParameterListWidget
-------------------
Scrollable list of VariableCard widgets.

Responsibility
~~~~~~~~~~~~~~
* Holds all cards in order.
* Listens to every card's ``code_changed`` signal.
* On any change, assembles the full class body and writes the file via the
  ``_write_callback`` supplied at construction.

The file structure that is written back looks like::

    class <ClassName>(<BaseClassName>):

        <field 1 code>

        <field 2 code>

        def update(self):
            ...
"""

from __future__ import annotations

import copy
from typing import Callable

from chemunited.qt.shared.widgets.base_mode_editor.cards.builder_models import BasicVariableBuildMode
from pydantic import BaseModel
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QScrollArea, QVBoxLayout, QWidget

from .cards import VariableCard


class ParameterListWidget(QScrollArea):
    """
    Scrollable list of VariableCard widgets.

    Parameters
    ----------
    class_name:
        Name of the generated class, e.g. ``"MainParameters"``.
    base_class_name:
        Name of the base class, e.g. ``"BaseModel"`` or ``"BaseModeParameters"``.
    write_callback:
        Called with the full class source string whenever any card changes.
        Typically this splices the string back into the file on disk.
    parent:
        Qt parent widget.
    """

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

        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(10, 10, 10, 10)
        self._layout.setSpacing(8)
        self._layout.addStretch()  # kept at bottom

        self.setWidget(self._container)
        self._cards: list[VariableCard] = []
        self._loading: bool = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def begin_load(self) -> None:
        """Suppress _flush() during bulk card population."""
        self._loading = True

    def end_load(self) -> None:
        """Re-enable _flush() after bulk population (does not flush itself)."""
        self._loading = False

    def add_card(self, mode: BasicVariableBuildMode) -> VariableCard:
        card = VariableCard(mode, self._container)
        card.deleted.connect(self._remove_card)
        card.duplicate.connect(self._duplicate_card)
        card.code_changed.connect(self._on_any_card_changed)
        # Insert before the trailing stretch (always the last layout item)
        self._layout.insertWidget(self._layout.count() - 1, card)
        self._cards.append(card)
        self._flush()
        return card

    def build_source(self) -> str:
        """Return the field-definitions block for the class, or '' if any card is invalid."""
        if not self._cards:
            return f"class {self._class_name}({self._base_class_name}):\n    pass\n"
        snippets = [card.get_field_code() for card in self._cards]
        if any(s == "" for s in snippets):
            return ""
        body = "\n\n".join(snippets)
        return (
            f"class {self._class_name}({self._base_class_name}):\n\n"
            f"{body}\n"
        )

    def validate_all(self) -> bool:
        return all(card.validate() for card in self._cards)

    def clear_all(self) -> None:
        self._loading = True
        try:
            for card in list(self._cards):
                self._remove_card(card)
        finally:
            self._loading = False

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _flush(self) -> None:
        if self._loading:
            return
        source = self.build_source()
        if source and self._write_callback:
            self._write_callback(source)

    def _on_any_card_changed(self, _snippet: str) -> None:
        self._flush()

    def _remove_card(self, card: VariableCard) -> None:
        self._cards.remove(card)
        self._layout.removeWidget(card)
        card.deleteLater()
        self._flush()

    def _duplicate_card(self, card: VariableCard) -> None:
        self.add_card(copy.deepcopy(card.mode))
