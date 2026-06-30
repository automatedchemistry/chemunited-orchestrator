"""Widget to manage the inventory content of each component."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from copy import deepcopy
from dataclasses import dataclass
from math import isfinite
from typing import TYPE_CHECKING

from chemunited_core.common.enums import PhaseKind
from chemunited_core.compounds import COMPOUNDS
from PyQt5.QtCore import QSize, Qt
from PyQt5.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    ComboBox,
    DoubleSpinBox,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    ListWidget,
    PrimaryPushButton,
    PushButton,
    StrongBodyLabel,
)
from qframelesswindow import FramelessDialog

from chemunited.orchestrator.inventory_state import ensure_air_defaults

if TYPE_CHECKING:
    from chemunited.elements.component import ElectronicManager, UtensilManager

ComponentProvider = Callable[
    [], Iterable[tuple[str, "UtensilManager | ElectronicManager"]]
]

_ROW_HEIGHT = 34
_VOLUME_ML_TO_M3 = 1e-6
_VOLUME_M3_TO_ML = 1e6
_MAX_VALUE = 1e18
_UNIT_MOL = "mol"
_UNIT_ML = "ml"
_UNLIMITED_CAPACITY_ML = 1e9


@dataclass
class _InventoryEntry:
    component_name: str
    inventory_key: str
    manager: UtensilManager | ElectronicManager
    component_data: object
    live_inventory: object
    draft_inventory: object

    @property
    def key(self) -> tuple[str, str]:
        return self.component_name, self.inventory_key


class InventoryStatusWidget(QWidget):
    """Draft editor for component inventory contents built from registered compounds."""

    def __init__(
        self,
        component_provider: ComponentProvider | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._component_provider = component_provider or (lambda: [])
        self._entries: list[_InventoryEntry] = []
        self._amount_spins: dict[str, DoubleSpinBox] = {}
        self._loading = False
        self._active_entry_index = -1
        self._active_phase = PhaseKind.LIQUID
        self._active_amount_unit = _UNIT_MOL
        self._setup_ui()
        self._connect_signals()
        self.sync()

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(16)

        left_panel = QWidget(self)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)
        left_layout.addWidget(StrongBodyLabel("Component inventories", self))

        self.inventory_list = ListWidget(self)
        self.inventory_list.setAlternatingRowColors(True)
        left_layout.addWidget(self.inventory_list, stretch=1)

        right_panel = QWidget(self)
        editor_layout = QVBoxLayout(right_panel)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(12)

        self.title_label = StrongBodyLabel("Inventory content", self)
        editor_layout.addWidget(self.title_label)

        self.capacity_label = CaptionLabel("", self)
        self.capacity_label.setWordWrap(True)
        editor_layout.addWidget(self.capacity_label)

        controls = QWidget(self)
        controls_layout = QGridLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setHorizontalSpacing(8)
        controls_layout.setVerticalSpacing(8)

        controls_layout.addWidget(BodyLabel("Phase", self), 0, 0)
        self.phase_combo = ComboBox(self)
        for phase in (PhaseKind.LIQUID, PhaseKind.GAS):
            self.phase_combo.addItem(phase.value, userData=phase)
        controls_layout.addWidget(self.phase_combo, 0, 1)

        controls_layout.addWidget(BodyLabel("Volume (ml)", self), 1, 0)
        self.volume_spin = DoubleSpinBox(self)
        self.volume_spin.setRange(0.0, _MAX_VALUE)
        self.volume_spin.setDecimals(6)
        self.volume_spin.setSingleStep(0.1)
        controls_layout.addWidget(self.volume_spin, 1, 1)

        controls_layout.addWidget(BodyLabel("Amount unit", self), 2, 0)
        self.amount_unit_combo = ComboBox(self)
        self.amount_unit_combo.addItem("mol", userData=_UNIT_MOL)
        self.amount_unit_combo.addItem("ml", userData=_UNIT_ML)
        controls_layout.addWidget(self.amount_unit_combo, 2, 1)

        editor_layout.addWidget(controls)

        self.species_frame = QFrame(self)
        self.species_layout = QGridLayout(self.species_frame)
        self.species_layout.setContentsMargins(0, 0, 0, 0)
        self.species_layout.setHorizontalSpacing(8)
        self.species_layout.setVerticalSpacing(6)
        self.species_layout.setColumnStretch(0, 1)
        self.species_layout.setColumnStretch(1, 2)
        editor_layout.addWidget(self.species_frame)

        editor_layout.addStretch()

        layout.addWidget(left_panel, stretch=1)
        layout.addWidget(right_panel, stretch=2)

    def _connect_signals(self) -> None:
        self.inventory_list.currentRowChanged.connect(  # type: ignore[attr-defined]
            self._on_context_changed
        )
        self.phase_combo.currentIndexChanged.connect(  # type: ignore[attr-defined]
            self._on_context_changed
        )
        self.amount_unit_combo.currentIndexChanged.connect(  # type: ignore[attr-defined]
            self._on_context_changed
        )

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.sync()

    def sync(self) -> None:
        selected = self._current_entry_key()
        self._loading = True
        self.inventory_list.clear()
        self._entries = []
        self._active_entry_index = -1

        for component_name, manager in self._component_provider():
            component_data = manager.inf
            ensure_air_defaults(component_data)
            inventories = getattr(component_data, "internal_inventories", {})
            for inventory_key, inventory in inventories.items():
                self._entries.append(
                    _InventoryEntry(
                        component_name=component_name,
                        inventory_key=inventory_key,
                        manager=manager,
                        component_data=component_data,
                        live_inventory=inventory,
                        draft_inventory=deepcopy(inventory),
                    )
                )
                text = self._entry_text(component_name, inventory_key)
                item = QListWidgetItem(text)
                item.setSizeHint(QSize(0, _ROW_HEIGHT))
                self.inventory_list.addItem(item)

        if selected is not None:
            for index, entry in enumerate(self._entries):
                if selected == entry.key:
                    self.inventory_list.setCurrentRow(index)
                    break

        if self.inventory_list.currentRow() < 0 and self._entries:
            self.inventory_list.setCurrentRow(0)

        self._loading = False
        self._sync_enabled_state()
        self._load_current_entry()

    def sync_compounds(self) -> None:
        self._load_current_entry()

    def commit(self) -> bool:
        if not self._save_visible_to_draft():
            return False
        if not self._validate_capacity():
            return False
        for entry in self._entries:
            self._copy_content(
                entry.live_inventory.liq_content,  # type: ignore[attr-defined]
                entry.draft_inventory.liq_content,  # type: ignore[attr-defined]
            )
            self._copy_content(
                entry.live_inventory.gas_content,  # type: ignore[attr-defined]
                entry.draft_inventory.gas_content,  # type: ignore[attr-defined]
            )
            ensure_air_defaults(entry.component_data)
        managers = {id(entry.manager): entry.manager for entry in self._entries}
        for manager in managers.values():
            manager.graph.sync_visuals()
        return True

    def visible_inventory_names(self) -> list[str]:
        return [
            self.inventory_list.item(i).text()
            for i in range(self.inventory_list.count())
        ]

    def species_names(self) -> list[str]:
        return list(self._amount_spins)

    def _sync_enabled_state(self) -> None:
        has_entries = bool(self._entries)
        self.phase_combo.setEnabled(has_entries)
        self.volume_spin.setEnabled(has_entries)
        self.amount_unit_combo.setEnabled(has_entries)

    def _on_context_changed(self, *_args) -> None:
        if self._loading:
            return
        if not self._save_visible_to_draft():
            return
        self._load_current_entry()

    def _load_current_entry(self, *_args) -> None:
        if self._loading:
            return
        entry = self._current_entry()
        self._clear_species_rows()
        self._sync_enabled_state()

        if entry is None:
            self.title_label.setText("Inventory content")
            self.capacity_label.setText("")
            self.capacity_label.setVisible(False)
            self.volume_spin.setValue(0.0)
            self.species_layout.addWidget(
                BodyLabel("No inventory-capable components.", self.species_frame),
                0,
                0,
                1,
                2,
            )
            self._active_entry_index = -1
            return

        phase = self._current_phase()
        content = self._content_for_phase(entry.draft_inventory, phase)
        self.title_label.setText(
            self._entry_text(entry.component_name, entry.inventory_key)
        )
        capacity_text = self._capacity_text(entry.component_data)
        self.capacity_label.setText(capacity_text)
        self.capacity_label.setVisible(bool(capacity_text))
        self.volume_spin.blockSignals(True)
        self.volume_spin.setValue(float(content.volume) * _VOLUME_M3_TO_ML)
        self.volume_spin.blockSignals(False)
        self._populate_species_rows(content.initial_species)
        self._active_entry_index = self.inventory_list.currentRow()
        self._active_phase = phase
        self._active_amount_unit = self._current_amount_unit()

    def _save_visible_to_draft(self) -> bool:
        if self._active_entry_index < 0 or self._active_entry_index >= len(
            self._entries
        ):
            return True
        entry = self._entries[self._active_entry_index]
        content = self._content_for_phase(entry.draft_inventory, self._active_phase)
        content.phase_kind = self._active_phase
        content.volume = self.volume_spin.value() * _VOLUME_ML_TO_M3
        species: dict[str, float] = {}
        for name, spin in self._amount_spins.items():
            value = spin.value()
            if value <= 0.0:
                continue
            try:
                species[name] = self._amount_to_moles(
                    name,
                    value,
                    self._active_amount_unit,
                    content,
                )
            except ValueError as exc:
                self._show_error("Invalid inventory amount", str(exc))
                return False
        content.initial_species = species
        return True

    @staticmethod
    def _copy_content(target, source) -> None:
        target.phase_kind = source.phase_kind
        target.volume = source.volume
        target.initial_species = dict(source.initial_species)

        # Pressure and temperature are intentionally not editable, but preserving
        # their draft values keeps future non-default core initialisation intact.
        target.initial_pressure = source.initial_pressure
        target.initial_temperature = source.initial_temperature

    def _populate_species_rows(self, values: dict[str, float]) -> None:
        names = COMPOUNDS.names
        if not names:
            self.species_layout.addWidget(
                BodyLabel("No registered compounds.", self.species_frame),
                0,
                0,
                1,
                2,
            )
            return

        self.species_layout.addWidget(BodyLabel("Compound", self.species_frame), 0, 0)
        self.species_layout.addWidget(
            BodyLabel("Amount", self.species_frame),
            0,
            1,
        )

        entry = self._current_entry()
        phase = self._current_phase()
        content = (
            self._content_for_phase(entry.draft_inventory, phase) if entry else None
        )

        for row, name in enumerate(names, start=1):
            label = QLabel(name, self.species_frame)
            spin = DoubleSpinBox(self.species_frame)
            spin.setRange(0.0, _MAX_VALUE)
            spin.setDecimals(9)
            spin.setSingleStep(0.001)
            spin.setMinimumWidth(240)
            spin.setValue(
                self._moles_to_amount(
                    name,
                    float(values.get(name, 0.0)),
                    self._current_amount_unit(),
                    content,
                )
            )
            self._amount_spins[name] = spin
            self.species_layout.addWidget(label, row, 0)
            self.species_layout.addWidget(spin, row, 1)

    def _clear_species_rows(self) -> None:
        self._amount_spins = {}
        while self.species_layout.count():
            item = self.species_layout.takeAt(0)
            widget = item.widget()  # type: ignore[union-attr]
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _current_entry(self) -> _InventoryEntry | None:
        row = self.inventory_list.currentRow()
        if row < 0 or row >= len(self._entries):
            return None
        return self._entries[row]

    def _current_entry_key(self) -> tuple[str, str] | None:
        entry = self._current_entry()
        if entry is None:
            return None
        return entry.key

    def _current_phase(self) -> PhaseKind:
        value = self.phase_combo.currentData()
        return value if isinstance(value, PhaseKind) else PhaseKind.LIQUID

    def _current_amount_unit(self) -> str:
        value = self.amount_unit_combo.currentData()
        return value if value in {_UNIT_MOL, _UNIT_ML} else _UNIT_MOL

    def _validate_capacity(self) -> bool:
        for entry in self._entries:
            capacity = self._capacity_limit_m3(entry.component_data)
            if capacity is None:
                continue
            total = float(entry.draft_inventory.liq_content.volume) + float(  # type: ignore[attr-defined]
                entry.draft_inventory.gas_content.volume  # type: ignore[attr-defined]
            )
            if total > capacity + 1e-15:
                self._show_error(
                    "Invalid inventory volume",
                    (
                        f"{entry.component_name} inventory volume exceeds "
                        f"component capacity ({capacity * _VOLUME_M3_TO_ML:g} ml)."
                    ),
                )
                return False
        return True

    @classmethod
    def _capacity_text(cls, component_data: object) -> str:
        capacity = float(getattr(component_data, "capacity_value", 0.0) or 0.0)
        if capacity <= 0.0 or not isfinite(capacity):
            return ""
        capacity_ml = capacity * _VOLUME_M3_TO_ML
        if capacity_ml >= _UNLIMITED_CAPACITY_ML:
            return "Capacity: not limited"
        if capacity_ml >= 1000.0:
            return f"Capacity: {capacity_ml / 1000.0:g} L"
        return f"Capacity: {capacity_ml:g} ml"

    @staticmethod
    def _capacity_limit_m3(component_data: object) -> float | None:
        capacity = float(getattr(component_data, "capacity_value", 0.0) or 0.0)
        if capacity <= 0.0 or not isfinite(capacity):
            return None
        if capacity * _VOLUME_M3_TO_ML >= _UNLIMITED_CAPACITY_ML:
            return None
        return capacity

    def _amount_to_moles(self, name: str, value: float, unit: str, content) -> float:
        if unit == _UNIT_MOL:
            return value
        return value * _VOLUME_ML_TO_M3 / self._molar_volume(name, content)

    def _moles_to_amount(
        self,
        name: str,
        moles: float,
        unit: str,
        content,
    ) -> float:
        if unit == _UNIT_MOL or content is None or moles <= 0.0:
            return moles
        try:
            return moles * self._molar_volume(name, content) * _VOLUME_M3_TO_ML
        except ValueError:
            return 0.0

    def _molar_volume(self, name: str, content) -> float:
        entity = COMPOUNDS[name]
        if content.phase_kind == PhaseKind.LIQUID:
            return entity.molar_volume_liquid().magnitude
        return entity.molar_volume_gas(
            content.initial_temperature,
            content.initial_pressure,
        ).magnitude

    def _show_error(self, title: str, content: str) -> None:
        InfoBar.error(
            title=title,
            content=content,
            orient=Qt.Horizontal,  # type: ignore[attr-defined]
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=5000,
            parent=self.window(),
        )

    @staticmethod
    def _content_for_phase(inventory: object, phase: PhaseKind):
        if phase == PhaseKind.LIQUID:
            return inventory.liq_content  # type: ignore[attr-defined]
        return inventory.gas_content  # type: ignore[attr-defined]

    @staticmethod
    def _entry_text(component_name: str, inventory_key: str) -> str:
        return f"{component_name} / {inventory_key}"


class InventoryStatusDialog(FramelessDialog):
    """Modal inventory editor that commits draft changes on Save."""

    def __init__(
        self,
        component_provider: ComponentProvider | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self.setWindowTitle("Edit inventories")
        self.setResizeEnabled(True)
        self.resize(820, 520)

        self.inventory_widget = InventoryStatusWidget(
            component_provider=component_provider,
            parent=self,
        )

        self.vBoxLayout = QVBoxLayout(self)
        self.vBoxLayout.setContentsMargins(16, self.titleBar.height() + 16, 16, 16)
        self.vBoxLayout.setSpacing(12)
        self.vBoxLayout.addWidget(self.inventory_widget, stretch=1)

        footer = QHBoxLayout()
        footer.addStretch()
        self.cancel_button = PushButton("Cancel", self)
        self.save_button = PrimaryPushButton(FluentIcon.SAVE, "Save", self)
        footer.addWidget(self.cancel_button)
        footer.addWidget(self.save_button)
        self.vBoxLayout.addLayout(footer)

        self.cancel_button.clicked.connect(self.reject)  # type: ignore[attr-defined]
        self.save_button.clicked.connect(self._save)  # type: ignore[attr-defined]

    def _save(self) -> None:
        if self.inventory_widget.commit():
            self.accept()
