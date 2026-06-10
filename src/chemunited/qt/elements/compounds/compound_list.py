from __future__ import annotations

import re

from chemunited_core.compounds import COMPOUNDS, ChemicalEntity
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    ListWidget,
    PrimaryPushButton,
    PushButton,
    StrongBodyLabel,
)

from chemunited.qt.orchestrator.protocols import is_valid_name

_BUILT_IN_COMPOUNDS = {"air"}
_HEX_COLOR_RE = re.compile(r"#[0-9A-Fa-f]{6}")


class CompoundList(QWidget):
    """Runtime editor for the project-wide in-memory compound registry."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()
        self._connect_signals()
        self.sync()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(12)

        layout.addWidget(StrongBodyLabel("Available compounds", self))

        self.list_widget = ListWidget(self)
        self.list_widget.setAlternatingRowColors(True)
        layout.addWidget(self.list_widget, stretch=1)

        self.remove_button = PushButton(FluentIcon.DELETE, "Remove selected", self)
        self.remove_button.setToolTip("Remove the selected user-added compound")
        layout.addWidget(
            self.remove_button,
            alignment=Qt.AlignLeft,  # type: ignore[arg-type]
        )

        layout.addSpacing(8)
        layout.addWidget(StrongBodyLabel("Add compound", self))

        self.name_edit = LineEdit(self)
        self.name_edit.setPlaceholderText("compound_name")
        self.molecular_weight_edit = LineEdit(self)
        self.molecular_weight_edit.setPlaceholderText("g/mol")
        self.cp_liquid_edit = LineEdit(self)
        self.cp_liquid_edit.setPlaceholderText("optional, J/(mol K)")
        self.cp_gas_edit = LineEdit(self)
        self.cp_gas_edit.setPlaceholderText("optional, J/(mol K)")
        self.density_liquid_edit = LineEdit(self)
        self.density_liquid_edit.setPlaceholderText("optional, kg/m^3")
        self.color_edit = LineEdit(self)
        self.color_edit.setPlaceholderText("optional, #RRGGBB")
        self.color_preview = QWidget(self)
        self.color_preview.setFixedSize(28, 20)
        self._update_color_preview()

        color_row = QHBoxLayout()
        color_row.setContentsMargins(0, 0, 0, 0)
        color_row.setSpacing(8)
        color_row.addWidget(self.color_edit, stretch=1)
        color_row.addWidget(self.color_preview)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(8)
        form.addRow(BodyLabel("Name", self), self.name_edit)
        form.addRow(BodyLabel("Molecular weight", self), self.molecular_weight_edit)
        form.addRow(BodyLabel("Cp liquid", self), self.cp_liquid_edit)
        form.addRow(BodyLabel("Cp gas", self), self.cp_gas_edit)
        form.addRow(BodyLabel("Liquid density", self), self.density_liquid_edit)
        form.addRow(BodyLabel("Color", self), color_row)
        layout.addLayout(form)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        self.add_button = PrimaryPushButton(FluentIcon.ADD, "Add compound", self)
        self.clear_button = PushButton("Clear", self)
        button_row.addWidget(self.add_button)
        button_row.addWidget(self.clear_button)
        button_row.addStretch()
        layout.addLayout(button_row)

    def _connect_signals(self) -> None:
        self.add_button.clicked.connect(self.add_compound)  # type: ignore[attr-defined]
        self.clear_button.clicked.connect(self.clear_form)  # type: ignore[attr-defined]
        self.remove_button.clicked.connect(  # type: ignore[attr-defined]
            self.remove_selected_compound
        )
        self.list_widget.currentItemChanged.connect(  # type: ignore[attr-defined]
            self._update_remove_button
        )
        self.color_edit.textChanged.connect(  # type: ignore[attr-defined]
            self._update_color_preview
        )

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.sync()

    def sync(self) -> None:
        selected = self.selected_name()
        self.list_widget.clear()

        for entity in COMPOUNDS.entities:
            item = QListWidgetItem(entity.name)
            item.setToolTip(self._compound_tooltip(entity))
            if entity.color_alpha > 0:
                item.setForeground(QColor(entity.rgb_hex))
            self.list_widget.addItem(item)

        if selected is not None:
            matches = self.list_widget.findItems(  # type: ignore[arg-type]
                selected,
                Qt.MatchExactly,
            )
            if matches:
                self.list_widget.setCurrentItem(matches[0])

        self._update_remove_button()

    def selected_name(self) -> str | None:
        item = self.list_widget.currentItem()
        return item.text() if item is not None else None

    def visible_names(self) -> list[str]:
        return [
            self.list_widget.item(i).text() for i in range(self.list_widget.count())
        ]

    def add_compound(self) -> None:
        try:
            entity = self._entity_from_form()
        except ValueError as exc:
            self._show_warning(str(exc))
            return

        COMPOUNDS.register(entity)
        self.clear_form()
        self.sync()
        self._select_name(entity.name)
        self._show_success(f"Compound {entity.name!r} added.")

    def remove_selected_compound(self) -> None:
        name = self.selected_name()
        if name is None:
            self._show_warning("Select a compound to remove.")
            return
        if name in _BUILT_IN_COMPOUNDS:
            self._show_warning(f"Built-in compound {name!r} cannot be removed.")
            return

        remaining = [entity for entity in COMPOUNDS.entities if entity.name != name]
        if len(remaining) == len(COMPOUNDS.entities):
            self._show_warning(f"Compound {name!r} is not registered.")
            return

        COMPOUNDS.clear()
        for entity in remaining:
            if entity.name not in _BUILT_IN_COMPOUNDS:
                COMPOUNDS.register(entity)

        self.sync()
        self._show_success(f"Compound {name!r} removed.")

    def clear_form(self) -> None:
        for edit in (
            self.name_edit,
            self.molecular_weight_edit,
            self.cp_liquid_edit,
            self.cp_gas_edit,
            self.density_liquid_edit,
            self.color_edit,
        ):
            edit.clear()
        self._update_color_preview()

    def _entity_from_form(self) -> ChemicalEntity:
        name = self.name_edit.text().strip()
        if not name:
            raise ValueError("Compound name is required.")
        if not is_valid_name(name):
            raise ValueError(
                "Compound name may contain only letters, numbers, _ and -."
            )
        if name in COMPOUNDS:
            raise ValueError(f"A compound named {name!r} already exists.")

        color_text = self.color_edit.text().strip()
        if color_text and _HEX_COLOR_RE.fullmatch(color_text) is None:
            raise ValueError("Color must be blank or a hex value like #FF0000.")
        color_red, color_green, color_blue, color_alpha = self._rgba_from_hex(
            color_text
        )

        return ChemicalEntity(
            name=name,
            molecular_weight=self._required_positive_float(
                self.molecular_weight_edit.text(),
                "Molecular weight",
            ),
            cp_liquid=self._optional_positive_float(
                self.cp_liquid_edit.text(),
                "Cp liquid",
            ),
            cp_gas=self._optional_positive_float(
                self.cp_gas_edit.text(),
                "Cp gas",
            ),
            density_liquid=self._optional_positive_float(
                self.density_liquid_edit.text(),
                "Liquid density",
            ),
            color_red=color_red,
            color_green=color_green,
            color_blue=color_blue,
            color_alpha=color_alpha,
        )

    @staticmethod
    def _required_positive_float(value: str, label: str) -> float:
        text = value.strip()
        if not text:
            raise ValueError(f"{label} is required.")
        return CompoundList._positive_float(text, label)

    @staticmethod
    def _optional_positive_float(value: str, label: str) -> float:
        text = value.strip()
        if not text:
            return 0.0
        return CompoundList._nonnegative_float(text, label)

    @staticmethod
    def _positive_float(value: str, label: str) -> float:
        try:
            number = float(value)
        except ValueError as exc:
            raise ValueError(f"{label} must be a number.") from exc
        if number <= 0:
            raise ValueError(f"{label} must be positive.")
        return number

    @staticmethod
    def _nonnegative_float(value: str, label: str) -> float:
        try:
            number = float(value)
        except ValueError as exc:
            raise ValueError(f"{label} must be a number.") from exc
        if number < 0:
            raise ValueError(f"{label} must be greater than or equal to 0.")
        return number

    @staticmethod
    def _rgba_from_hex(value: str) -> tuple[int, int, int, int]:
        if not value:
            return (0, 0, 0, 0)
        return (
            int(value[1:3], 16),
            int(value[3:5], 16),
            int(value[5:7], 16),
            255,
        )

    @staticmethod
    def _compound_tooltip(entity: ChemicalEntity) -> str:
        values = [
            "Molecular weight: "
            f"{_format_quantity(entity.molecular_weight, 'g/mol')} g/mol",
            "Cp liquid: "
            f"{_format_quantity(entity.cp_liquid, 'J/(mol*K)')} J/(mol K)",
            "Cp gas: "
            f"{_format_quantity(entity.cp_gas, 'J/(mol*K)')} J/(mol K)",
            "Liquid density: "
            f"{_format_quantity(entity.density_liquid, 'kg/m^3')} kg/m^3",
        ]
        if entity.color_alpha > 0:
            values.append(f"Color: {entity.rgb_hex}")
        return "\n".join(values)

    def _update_color_preview(self) -> None:
        text = self.color_edit.text().strip()
        if _HEX_COLOR_RE.fullmatch(text):
            red, green, blue, alpha = self._rgba_from_hex(text)
            background = f"rgba({red}, {green}, {blue}, {alpha})"
        else:
            background = "transparent"
        self.color_preview.setStyleSheet(
            "border: 1px solid palette(mid);"
            "border-radius: 3px;"
            f"background-color: {background};"
        )

    def _select_name(self, name: str) -> None:
        matches = self.list_widget.findItems(  # type: ignore[arg-type]
            name,
            Qt.MatchExactly,
        )
        if matches:
            self.list_widget.setCurrentItem(matches[0])

    def _update_remove_button(self, *_args) -> None:
        selected = self.selected_name()
        removable = selected is not None and selected not in _BUILT_IN_COMPOUNDS
        self.remove_button.setEnabled(removable)

    def _show_warning(self, message: str) -> None:
        InfoBar.warning(
            title="Invalid compound",
            content=message,
            orient=Qt.Horizontal,  # type: ignore[attr-defined]
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=3000,
            parent=self.window(),
        )

    def _show_success(self, message: str) -> None:
        InfoBar.success(
            title="Compounds",
            content=message,
            orient=Qt.Horizontal,  # type: ignore[attr-defined]
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=2000,
            parent=self.window(),
        )


def _format_quantity(value, unit: str) -> str:
    return f"{float(value.to(unit).magnitude):g}"
