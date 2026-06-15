from __future__ import annotations

from chemunited_core.compounds import COMPOUNDS, ChemicalEntity
from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    ListWidget,
    PrimaryPushButton,
    PushButton,
    StrongBodyLabel,
)

from chemunited.qt.orchestrator.protocols import is_valid_name

from .compound_dialog import CompoundDialog

_BUILT_IN_COMPOUNDS = {"air"}
_ROW_HEIGHT = 34
_SWATCH_SIZE = 14


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

        self._add_button = PrimaryPushButton(FluentIcon.ADD, "Add compound", self)
        layout.addWidget(self._add_button, alignment=Qt.AlignLeft)  # type: ignore[arg-type]

    def _connect_signals(self) -> None:
        self._add_button.clicked.connect(self._open_add_dialog)  # type: ignore[attr-defined]
        self.remove_button.clicked.connect(  # type: ignore[attr-defined]
            self.remove_selected_compound
        )
        self.list_widget.currentItemChanged.connect(  # type: ignore[attr-defined]
            self._update_remove_button
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
            item.setSizeHint(QSize(0, _ROW_HEIGHT))
            item.setForeground(QColor(0, 0, 0, 0))
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(
                item, _CompoundRowWidget(entity, self.list_widget)
            )

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

    def _open_add_dialog(self) -> None:
        dialog = CompoundDialog(parent=self.window())
        if not dialog.exec_():
            return
        entity = dialog.get_result_instance()
        if entity is None:
            return
        if not is_valid_name(entity.name):
            self._show_warning(
                "Compound name may contain only letters, numbers, _ and -."
            )
            return
        if entity.name in COMPOUNDS:
            self._show_warning(f"A compound named {entity.name!r} already exists.")
            return
        COMPOUNDS.register(entity)
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


class _CompoundRowWidget(QWidget):
    def __init__(self, entity: ChemicalEntity, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName(f"compound-row-{entity.name}")
        self.setFixedHeight(_ROW_HEIGHT)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignVCenter)  # type: ignore[arg-type]

        swatch = QFrame(self)
        swatch.setObjectName("compound-color-swatch")
        swatch.setFixedSize(_SWATCH_SIZE, _SWATCH_SIZE)
        swatch.setToolTip(_swatch_tooltip(entity))
        swatch.setStyleSheet(_swatch_stylesheet(entity))
        layout.addWidget(swatch, alignment=Qt.AlignVCenter)  # type: ignore[arg-type]

        label = QLabel(entity.name, self)
        label.setObjectName("compound-name-label")
        label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)  # type: ignore[arg-type]
        layout.addWidget(label, stretch=1, alignment=Qt.AlignVCenter)  # type: ignore[arg-type]


def _swatch_stylesheet(entity: ChemicalEntity) -> str:
    if not _has_swatch_color(entity):
        return (
            "QFrame#compound-color-swatch {"
            "background: transparent;"
            "border: 1px solid rgba(120, 120, 120, 120);"
            "border-radius: 3px;"
            "}"
        )

    alpha = entity.color_alpha if entity.color_alpha > 0 else 255
    return (
        "QFrame#compound-color-swatch {"
        f"background-color: rgba({entity.color_red}, {entity.color_green}, "
        f"{entity.color_blue}, {alpha});"
        "border: 1px solid rgba(0, 0, 0, 60);"
        "border-radius: 3px;"
        "}"
    )


def _has_swatch_color(entity: ChemicalEntity) -> bool:
    return entity.color_alpha > 0 or any(
        channel > 0
        for channel in (entity.color_red, entity.color_green, entity.color_blue)
    )


def _swatch_tooltip(entity: ChemicalEntity) -> str:
    if not _has_swatch_color(entity):
        return "No color"
    if entity.color_alpha > 0:
        return entity.rgba_hex
    return f"{entity.rgb_hex} (opaque preview; alpha is 0)"
