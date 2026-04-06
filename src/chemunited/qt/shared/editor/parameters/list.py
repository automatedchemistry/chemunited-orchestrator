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

    # Script file of project parameter
    # ...header lines from the original file...
    from chemunited.utils.base_project_config import BaseModeParameters
    from chemunited.utils.quantity import ChemQuantityValidator
    from chemunited import ChemUnitQuantity
    from typing import Annotated
    from pydantic import Field


    class <ClassName>(BaseModeParameters):

        <field 1 code>

        <field 2 code>

        def update(self):
            ...
"""

from __future__ import annotations

import copy
from typing import Callable

from pydantic import BaseModel
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QScrollArea, QVBoxLayout, QWidget

from .cards import VariableCard

# Fixed imports that every generated parameters file needs.
_FILE_HEADER = """\
# Script file of project parameter
from chemunited.utils.base_project_config import BaseModeParameters
from chemunited.utils.quantity import ChemQuantityValidator
from chemunited import ChemUnitQuantity
from typing import Annotated
from pydantic import Field
"""

_UPDATE_METHOD = """\

    def update(self):
        ...
"""


class ParameterListWidget(QScrollArea):
    """
    Scrollable list of VariableCard widgets.

    Parameters
    ----------
    class_name:
        Name of the generated class, e.g. ``"MainParameters"``.
    write_callback:
        Called with the full Python source string whenever any card changes.
        Typically this writes the string back to disk.
    parent:
        Qt parent widget.
    """

    def __init__(
        self,
        class_name: str = "MainParameters",
        write_callback: Callable[[str], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._class_name = class_name
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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_card(self, mode: BaseModel) -> VariableCard:
        """Create a VariableCard for *mode* and append it to the list."""
        card = VariableCard(mode, parent=self._container)
        card.deleted.connect(self._remove_card)
        card.duplicate.connect(self._duplicate_card)
        card.code_changed.connect(self._on_any_card_changed)

        self._layout.insertWidget(self._layout.count() - 1, card)
        self._cards.append(card)
        self._flush()
        return card

    def validate_all(self) -> bool:
        """Validate every card. Returns True only if all pass."""
        return all(card.validate() for card in self._cards)

    def clear_all(self) -> None:
        """Remove all cards."""
        for card in list(self._cards):
            self._remove_card(card)

    def set_class_name(self, name: str) -> None:
        self._class_name = name
        self._flush()

    def build_source(self) -> str:
        """
        Assemble and return the full Python source for the parameters file.
        Returns an empty string if any card is currently invalid.
        """
        snippets = [card.get_field_code() for card in self._cards]
        if any(s == "" for s in snippets):
            return ""

        body = "\n\n".join(snippets)
        return (
            f"{_FILE_HEADER}\n\n"
            f"class {self._class_name}(BaseModeParameters):\n\n"
            f"{body}\n"
            f"{_UPDATE_METHOD}"
        )

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _on_any_card_changed(self, _snippet: str) -> None:
        self._flush()

    def _flush(self) -> None:
        """Regenerate source and call the write callback."""
        if self._write_callback is None:
            return
        source = self.build_source()
        if source:
            self._write_callback(source)

    def _remove_card(self, card: VariableCard) -> None:
        self._layout.removeWidget(card)
        self._cards.remove(card)
        card.deleteLater()
        self._flush()

    def _duplicate_card(self, card: VariableCard) -> None:
        self.add_card(copy.deepcopy(card.mode))
