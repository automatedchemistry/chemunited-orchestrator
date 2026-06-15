from __future__ import annotations

from chemunited_core.compounds import ChemicalEntity
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QHBoxLayout
from qfluentwidgets import FluentIcon, InfoBar, InfoBarPosition, PushButton

from chemunited.shared.widgets.base_mode_editor import BaseModeDialog

from . import coolprop_lookup


class CompoundDialog(BaseModeDialog):
    """Compound editor with optional CoolProp-assisted property fill."""

    def __init__(self, parent=None):
        super().__init__(
            ChemicalEntity,
            instance=ChemicalEntity(),
            title="Add Compound",
            parent=parent,
        )
        self._setup_coolprop_action()

    def _setup_coolprop_action(self) -> None:
        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)

        self.fill_from_coolprop_button = PushButton(
            FluentIcon.SYNC,
            "Fill from CoolProp",
            self,
        )
        self.fill_from_coolprop_button.setToolTip(
            "Fill available compound properties at 298.15 K and 101325 Pa"
        )
        self.fill_from_coolprop_button.clicked.connect(  # type: ignore[attr-defined]
            self._fill_from_coolprop
        )

        if not coolprop_lookup.is_coolprop_available():
            self.fill_from_coolprop_button.setEnabled(False)
            self.fill_from_coolprop_button.setToolTip(
                "Install the optional compound-lookup dependency to enable CoolProp"
            )

        action_row.addWidget(self.fill_from_coolprop_button)
        action_row.addStretch()
        self.vBoxLayout.insertLayout(
            self.vBoxLayout.indexOf(self.editor_widget), action_row
        )

    def _fill_from_coolprop(self) -> None:
        cards = self.editor_widget._cards
        name_card = cards.get("name")
        compound_name = str(name_card.get_value()).strip() if name_card else ""

        try:
            result = coolprop_lookup.lookup_compound_properties(compound_name)
        except ImportError:
            self._show_warning("CoolProp is not installed.")
            return
        except ValueError as exc:
            self._show_warning(str(exc))
            return

        filled = 0
        for field_name, value in result.values.items():
            card = cards.get(field_name)
            if card is None:
                continue
            card.set_value(value)
            filled += 1

        if filled == 0:
            self._show_warning(f"No CoolProp properties found for {compound_name!r}.")
            return

        self._show_success(
            f"Filled {filled} properties from CoolProp fluid {result.fluid_name!r}."
        )

    def _show_warning(self, message: str) -> None:
        InfoBar.warning(
            title="CoolProp",
            content=message,
            orient=Qt.Horizontal,  # type: ignore[attr-defined]
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=3000,
            parent=self,
        )

    def _show_success(self, message: str) -> None:
        InfoBar.success(
            title="CoolProp",
            content=message,
            orient=Qt.Horizontal,  # type: ignore[attr-defined]
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=2000,
            parent=self,
        )
