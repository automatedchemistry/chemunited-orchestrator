"""Workspace for configuring the initial contents of component inventories."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from copy import deepcopy
from dataclasses import dataclass
from math import isfinite
from typing import TYPE_CHECKING

from PyQt5.QtCore import QItemSelectionModel, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPen
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    ComboBox,
    DoubleSpinBox,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    PrimaryPushButton,
    PushButton,
    SearchLineEdit,
    StrongBodyLabel,
    SwitchButton,
    TableWidget,
    ToolButton,
)

from chemunited.orchestrator.inventory_state import ensure_air_defaults
from chemunited_core.common.enums import PhaseKind
from chemunited_core.components.internals import InventoryNode
from chemunited_core.compounds import COMPOUNDS, VolumeContentBase

if TYPE_CHECKING:
    from chemunited.elements.component import ElectronicManager, UtensilManager

    ComponentManager = UtensilManager | ElectronicManager
else:
    ComponentManager = object
ComponentProvider = Callable[[], Iterable[tuple[str, ComponentManager]]]
InventoryId = tuple[int, str]

_M3_TO_ML = 1e6
_ML_TO_M3 = 1e-6
_MAX_VALUE = 1e18
_UNLIMITED_CAPACITY_ML = 1e9
_CAPACITY_TOLERANCE_M3 = 1e-15

_UNIT_MOL = "mol"
_UNIT_MMOL = "mmol"
_UNIT_MOLAR = "mol/L"
_UNIT_EQUIVALENT_ML = "equiv. mL"


def inventory_capacity_m3(component_data: object) -> float | None:
    """Return a component's finite inventory capacity in cubic metres."""

    raw_capacity = getattr(component_data, "capacity_value", None)
    if raw_capacity is not None:
        try:
            capacity = float(raw_capacity)
        except (TypeError, ValueError):
            capacity = 0.0
        if (
            isfinite(capacity)
            and capacity > 0.0
            and capacity * _M3_TO_ML < _UNLIMITED_CAPACITY_ML
        ):
            return capacity

    syringe_volume = getattr(component_data, "syringe_volume", None)
    if syringe_volume is not None:
        try:
            capacity = float(syringe_volume.to_base_units().magnitude)
        except (AttributeError, TypeError, ValueError):
            return None
        if isfinite(capacity) and capacity > 0.0:
            return capacity
    return None


def _format_volume(volume_m3: float) -> str:
    volume_ml = volume_m3 * _M3_TO_ML
    if abs(volume_ml) >= 1000.0:
        return f"{volume_ml / 1000.0:g} L"
    return f"{volume_ml:g} mL"


def _copy_content(target, source) -> None:
    target.phase_kind = source.phase_kind
    target.volume = source.volume
    target.initial_species = dict(source.initial_species)
    target.initial_pressure = source.initial_pressure
    target.initial_temperature = source.initial_temperature


@dataclass
class _InventoryEntry:
    component_name: str
    inventory_key: str
    manager: ComponentManager
    component_data: object
    live_inventory: InventoryNode
    draft_inventory: InventoryNode
    auto_headspace: bool

    @property
    def identity(self) -> InventoryId:
        return id(self.manager), self.inventory_key

    @property
    def capacity_m3(self) -> float | None:
        return inventory_capacity_m3(self.component_data)


class _CapacityBar(QWidget):
    """Compact liquid/gas/remaining capacity visualization."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._liquid = 0.0
        self._gas = 0.0
        self._capacity: float | None = None
        self.setFixedHeight(14)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_values(
        self,
        liquid_m3: float,
        gas_m3: float,
        capacity_m3: float | None,
    ) -> None:
        self._liquid = max(0.0, liquid_m3)
        self._gas = max(0.0, gas_m3)
        self._capacity = capacity_m3
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.setBrush(QColor(120, 120, 120, 28))
        painter.setPen(QPen(QColor(120, 120, 120, 100), 1))
        painter.drawRoundedRect(rect, 4, 4)

        capacity = self._capacity
        if capacity is None or capacity <= 0.0:
            total = self._liquid + self._gas
            if total <= 0.0:
                return
            capacity = total

        total = self._liquid + self._gas
        available_width = max(0, rect.width())
        liquid_width = min(
            available_width, round(available_width * self._liquid / capacity)
        )
        gas_width = min(
            available_width - liquid_width,
            round(available_width * self._gas / capacity),
        )

        if liquid_width:
            liquid_rect = rect.adjusted(0, 0, -(available_width - liquid_width), 0)
            painter.setPen(Qt.NoPen)  # type: ignore[arg-type, attr-defined]
            painter.setBrush(QColor("#3b82f6"))
            painter.drawRoundedRect(liquid_rect, 4, 4)
        if gas_width:
            gas_rect = rect.adjusted(
                liquid_width,
                0,
                -(available_width - liquid_width - gas_width),
                0,
            )
            painter.setPen(Qt.NoPen)  # type: ignore[arg-type, attr-defined]
            painter.setBrush(QColor("#94a3b8"))
            painter.drawRect(gas_rect)
        if total > capacity + _CAPACITY_TOLERANCE_M3:
            painter.setBrush(Qt.NoBrush)  # type: ignore[arg-type, attr-defined]
            painter.setPen(QPen(QColor("#dc2626"), 2))
            painter.drawRoundedRect(rect, 4, 4)


class _CompositionRow(QFrame):
    changed = pyqtSignal()
    remove_requested = pyqtSignal(str)

    def __init__(
        self,
        compound_name: str,
        moles: float,
        phase: PhaseKind,
        content_provider: Callable[[], VolumeContentBase],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.compound_name = compound_name
        self._moles = max(0.0, float(moles))
        self._phase = phase
        self._content_provider = content_provider
        self._unit = _UNIT_MOL
        self._loading = False

        layout = QGridLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setHorizontalSpacing(6)

        self.name_label = BodyLabel(compound_name, self)
        layout.addWidget(self.name_label, 0, 0)

        self.amount_spin = DoubleSpinBox(self)
        self.amount_spin.setRange(0.0, _MAX_VALUE)
        self.amount_spin.setDecimals(9)
        self.amount_spin.setSingleStep(0.001)
        self.amount_spin.setMinimumWidth(120)
        layout.addWidget(self.amount_spin, 0, 1)

        self.unit_combo = ComboBox(self)
        for unit in (_UNIT_MOL, _UNIT_MMOL, _UNIT_MOLAR):
            self.unit_combo.addItem(unit, userData=unit)
        if self._supports_equivalent_volume():
            self.unit_combo.addItem(
                "equiv. mL",
                userData=_UNIT_EQUIVALENT_ML,
            )
        layout.addWidget(self.unit_combo, 0, 2)

        self.remove_button = ToolButton(FluentIcon.REMOVE, self)
        self.remove_button.setToolTip(f"Remove {compound_name}")
        self.remove_button.setFixedSize(34, 34)
        layout.addWidget(self.remove_button, 0, 3)

        self.amount_spin.valueChanged.connect(self._on_amount_changed)  # type: ignore[attr-defined]
        self.unit_combo.currentIndexChanged.connect(self._on_unit_changed)  # type: ignore[attr-defined]
        self.remove_button.clicked.connect(  # type: ignore[attr-defined]
            lambda: self.remove_requested.emit(self.compound_name)
        )
        self.refresh_display()

    def moles(self) -> float:
        if not self._loading:
            self._moles = self._display_to_moles(self.amount_spin.value(), self._unit)
        return max(0.0, self._moles)

    def refresh_display(self) -> None:
        self._loading = True
        concentration_without_volume = (
            self._unit == _UNIT_MOLAR and self._phase_volume_m3() <= 0.0
        )
        self.amount_spin.setEnabled(not concentration_without_volume)
        self.amount_spin.setToolTip(
            "Set the phase volume before entering a concentration."
            if concentration_without_volume
            else ""
        )
        self.amount_spin.setValue(self._moles_to_display(self._moles, self._unit))
        self._loading = False

    def _on_amount_changed(self, value: float) -> None:
        if self._loading:
            return
        self._moles = self._display_to_moles(value, self._unit)
        self.changed.emit()

    def _on_unit_changed(self, _index: int) -> None:
        if self._loading:
            return
        unit = self.unit_combo.currentData()
        if not isinstance(unit, str):
            return
        self._unit = unit
        self.refresh_display()
        self.changed.emit()

    def _phase_volume_m3(self) -> float:
        return max(0.0, float(getattr(self._content_provider(), "volume", 0.0)))

    def _supports_equivalent_volume(self) -> bool:
        try:
            self._molar_volume_m3_per_mol()
        except (KeyError, ValueError):
            return False
        return True

    def _molar_volume_m3_per_mol(self) -> float:
        entity = COMPOUNDS[self.compound_name]
        content = self._content_provider()
        if self._phase == PhaseKind.LIQUID:
            return float(entity.molar_volume_liquid().magnitude)
        return float(
            entity.molar_volume_gas(
                content.initial_temperature,
                content.initial_pressure,
            ).magnitude
        )

    def _display_to_moles(self, value: float, unit: str) -> float:
        if unit == _UNIT_MMOL:
            return value / 1000.0
        if unit == _UNIT_MOLAR:
            return value * self._phase_volume_m3() * 1000.0
        if unit == _UNIT_EQUIVALENT_ML:
            return value * _ML_TO_M3 / self._molar_volume_m3_per_mol()
        return value

    def _moles_to_display(self, moles: float, unit: str) -> float:
        if unit == _UNIT_MMOL:
            return moles * 1000.0
        if unit == _UNIT_MOLAR:
            volume_l = self._phase_volume_m3() * 1000.0
            return moles / volume_l if volume_l > 0.0 else 0.0
        if unit == _UNIT_EQUIVALENT_ML:
            return moles * self._molar_volume_m3_per_mol() * _M3_TO_ML
        return moles


class _PhaseEditor(CardWidget):
    changed = pyqtSignal()
    volume_changed = pyqtSignal(float)

    def __init__(
        self,
        title: str,
        phase: PhaseKind,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.phase = phase
        self._content: VolumeContentBase | None = None
        self._rows: dict[str, _CompositionRow] = {}
        self._loading = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        layout.addWidget(StrongBodyLabel(title, self))

        volume_row = QHBoxLayout()
        volume_row.addWidget(BodyLabel("Volume", self))
        volume_row.addStretch()
        self.volume_spin = DoubleSpinBox(self)
        self.volume_spin.setRange(0.0, _MAX_VALUE)
        self.volume_spin.setDecimals(6)
        self.volume_spin.setSingleStep(0.1)
        self.volume_spin.setSuffix(" mL")
        self.volume_spin.setMinimumWidth(150)
        volume_row.addWidget(self.volume_spin)
        layout.addLayout(volume_row)

        layout.addWidget(CaptionLabel("Composition", self))
        self.composition_widget = QWidget(self)
        self.composition_layout = QVBoxLayout(self.composition_widget)
        self.composition_layout.setContentsMargins(0, 0, 0, 0)
        self.composition_layout.setSpacing(4)
        layout.addWidget(self.composition_widget)

        self.empty_label = CaptionLabel("No compounds in this phase.", self)
        self.composition_layout.addWidget(self.empty_label)

        add_row = QHBoxLayout()
        self.add_combo = ComboBox(self)
        self.add_combo.setMinimumWidth(150)
        self.add_button = PushButton(FluentIcon.ADD, "Add compound", self)
        add_row.addWidget(self.add_combo, stretch=1)
        add_row.addWidget(self.add_button)
        layout.addLayout(add_row)
        layout.addStretch()

        self.volume_spin.valueChanged.connect(self._on_volume_changed)  # type: ignore[attr-defined]
        self.add_button.clicked.connect(self._add_selected_compound)  # type: ignore[attr-defined]

    def load(self, content: VolumeContentBase) -> None:
        self._loading = True
        self._content = content
        self.volume_spin.setValue(
            max(0.0, float(getattr(content, "volume", 0.0))) * _M3_TO_ML
        )
        self._clear_rows()
        for name, moles in getattr(content, "initial_species", {}).items():
            if name in COMPOUNDS and float(moles) > 0.0:
                self._add_row(str(name), float(moles))
        self._refresh_add_choices()
        self._sync_empty_state()
        self._loading = False

    def save(self, content: VolumeContentBase) -> None:
        content.phase_kind = self.phase
        content.volume = self.volume_m3()
        content.initial_species = {
            name: moles
            for name, row in self._rows.items()
            if (moles := row.moles()) > 0.0
        }

    def volume_m3(self) -> float:
        return self.volume_spin.value() * _ML_TO_M3

    def set_volume_m3(self, volume_m3: float) -> None:
        self._loading = True
        self.volume_spin.setValue(max(0.0, volume_m3) * _M3_TO_ML)
        if self._content is not None:
            self._content.volume = max(0.0, volume_m3)
        for row in self._rows.values():
            row.refresh_display()
        self._loading = False

    def set_volume_read_only(self, read_only: bool) -> None:
        self.volume_spin.setReadOnly(read_only)
        self.volume_spin.setToolTip(
            "Calculated from capacity and liquid volume." if read_only else ""
        )

    def refresh_compounds(self) -> None:
        removed = False
        for name in list(self._rows):
            if name in COMPOUNDS:
                continue
            row = self._rows.pop(name)
            row.setParent(None)
            row.deleteLater()
            removed = True
        self._refresh_add_choices()
        self._sync_empty_state()
        if removed:
            self.changed.emit()

    def _on_volume_changed(self, value_ml: float) -> None:
        if self._loading:
            return
        if self._content is not None:
            self._content.volume = value_ml * _ML_TO_M3
        for row in self._rows.values():
            row.refresh_display()
        self.volume_changed.emit(value_ml * _ML_TO_M3)
        self.changed.emit()

    def _add_selected_compound(self) -> None:
        name = self.add_combo.currentData()
        if not isinstance(name, str) or name in self._rows:
            return
        self._add_row(name, 0.0)
        self._refresh_add_choices()
        self._sync_empty_state()
        self.changed.emit()

    def _add_row(self, name: str, moles: float) -> None:
        row = _CompositionRow(
            name,
            moles,
            self.phase,
            content_provider=self._current_content,
            parent=self.composition_widget,
        )
        row.changed.connect(self.changed)
        row.remove_requested.connect(self._remove_row)
        self._rows[name] = row
        self.composition_layout.addWidget(row)

    def _remove_row(self, name: str) -> None:
        row = self._rows.pop(name, None)
        if row is None:
            return
        row.setParent(None)
        row.deleteLater()
        self._refresh_add_choices()
        self._sync_empty_state()
        self.changed.emit()

    def _clear_rows(self) -> None:
        for row in self._rows.values():
            row.setParent(None)
            row.deleteLater()
        self._rows = {}

    def _refresh_add_choices(self) -> None:
        current = self.add_combo.currentData()
        self.add_combo.blockSignals(True)
        self.add_combo.clear()
        for name in COMPOUNDS.names:
            if name not in self._rows:
                self.add_combo.addItem(name, userData=name)
        if isinstance(current, str):
            index = self.add_combo.findData(current)
            if index >= 0:
                self.add_combo.setCurrentIndex(index)
        self.add_combo.blockSignals(False)
        self.add_button.setEnabled(self.add_combo.count() > 0)

    def _sync_empty_state(self) -> None:
        self.empty_label.setVisible(not self._rows)

    def _current_content(self) -> VolumeContentBase:
        if self._content is None:
            raise RuntimeError("Phase editor has no content")
        return self._content


class InventoryWorkspace(QWidget):
    """Persistent draft editor for all component initial inventories."""

    _HEADERS = (
        "Component",
        "Inventory / well",
        "Liquid",
        "Gas",
        "Capacity",
        "Composition",
        "Status",
    )

    def __init__(
        self,
        component_provider: ComponentProvider | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._component_provider = component_provider or (lambda: [])
        self._entries: list[_InventoryEntry] = []
        self._entry_by_id: dict[InventoryId, _InventoryEntry] = {}
        self._row_by_id: dict[InventoryId, int] = {}
        self._active_id: InventoryId | None = None
        self._loading = False
        self._dirty = False
        self._ui_ready = False
        self.sync(force=True)

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 18, 24, 18)
        root.setSpacing(12)

        title_row = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title_box.addWidget(StrongBodyLabel("Initial Inventory", self))
        title_box.addWidget(
            CaptionLabel(
                "Configure the liquid and gas contents used at the start of a run.",
                self,
            )
        )
        title_row.addLayout(title_box)
        title_row.addStretch()
        self.discard_button = PushButton("Discard changes", self)
        self.apply_button = PrimaryPushButton(
            FluentIcon.ACCEPT,
            "Apply changes",
            self,
        )
        title_row.addWidget(self.discard_button)
        title_row.addWidget(self.apply_button)
        root.addLayout(title_row)

        self.splitter = QSplitter(Qt.Horizontal, self)  # type: ignore[arg-type, attr-defined]
        root.addWidget(self.splitter, stretch=1)

        overview = QWidget(self.splitter)
        overview_layout = QVBoxLayout(overview)
        overview_layout.setContentsMargins(0, 0, 0, 0)
        overview_layout.setSpacing(8)

        self.search = SearchLineEdit(overview)
        self.search.setPlaceholderText("Search components, wells, or compounds")
        overview_layout.addWidget(self.search)

        self.table = TableWidget(overview)
        self.table.setColumnCount(len(self._HEADERS))
        self.table.setHorizontalHeaderLabels(self._HEADERS)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 130)
        self.table.setColumnWidth(1, 110)
        self.table.setColumnWidth(2, 80)
        self.table.setColumnWidth(3, 80)
        self.table.setColumnWidth(4, 80)
        self.table.setColumnWidth(5, 170)
        overview_layout.addWidget(self.table, stretch=1)

        bulk_row = QHBoxLayout()
        self.bulk_scope_combo = ComboBox(overview)
        for text in ("Both phases", "Liquid only", "Gas only"):
            self.bulk_scope_combo.addItem(text, userData=text)
        self.bulk_button = PushButton(
            FluentIcon.COPY,
            "Apply active to selection",
            overview,
        )
        bulk_row.addWidget(self.bulk_scope_combo)
        bulk_row.addWidget(self.bulk_button, stretch=1)
        overview_layout.addLayout(bulk_row)

        self.empty_overview_label = CaptionLabel(
            "No components with inventory storage are available.",
            overview,
        )
        self.empty_overview_label.setWordWrap(True)
        overview_layout.addWidget(self.empty_overview_label)

        editor_scroll = QScrollArea(self.splitter)
        editor_scroll.setWidgetResizable(True)
        editor_scroll.setFrameShape(QFrame.NoFrame)
        self.editor_content = QWidget(editor_scroll)
        editor_scroll.setWidget(self.editor_content)
        editor_layout = QVBoxLayout(self.editor_content)
        editor_layout.setContentsMargins(12, 0, 0, 0)
        editor_layout.setSpacing(10)

        self.editor_title = StrongBodyLabel("Select an inventory", self.editor_content)
        self.editor_subtitle = CaptionLabel("", self.editor_content)
        editor_layout.addWidget(self.editor_title)
        editor_layout.addWidget(self.editor_subtitle)

        capacity_card = CardWidget(self.editor_content)
        capacity_layout = QVBoxLayout(capacity_card)
        capacity_layout.setContentsMargins(16, 12, 16, 12)
        capacity_layout.setSpacing(6)
        capacity_heading = QHBoxLayout()
        capacity_heading.addWidget(StrongBodyLabel("Capacity", capacity_card))
        capacity_heading.addStretch()
        self.capacity_text = BodyLabel("", capacity_card)
        capacity_heading.addWidget(self.capacity_text)
        capacity_layout.addLayout(capacity_heading)
        self.capacity_bar = _CapacityBar(capacity_card)
        capacity_layout.addWidget(self.capacity_bar)
        self.capacity_detail = CaptionLabel("", capacity_card)
        capacity_layout.addWidget(self.capacity_detail)
        auto_row = QHBoxLayout()
        auto_row.addWidget(BodyLabel("Auto-fill gas headspace", capacity_card))
        auto_row.addStretch()
        self.auto_headspace_switch = SwitchButton(capacity_card)
        auto_row.addWidget(self.auto_headspace_switch)
        capacity_layout.addLayout(auto_row)
        editor_layout.addWidget(capacity_card)

        phase_row = QHBoxLayout()
        phase_row.setSpacing(10)
        self.liquid_editor = _PhaseEditor(
            "Liquid",
            PhaseKind.LIQUID,
            self.editor_content,
        )
        self.gas_editor = _PhaseEditor(
            "Gas",
            PhaseKind.GAS,
            self.editor_content,
        )
        phase_row.addWidget(self.liquid_editor, stretch=1)
        phase_row.addWidget(self.gas_editor, stretch=1)
        editor_layout.addLayout(phase_row)
        editor_layout.addStretch()

        self.splitter.addWidget(overview)
        self.splitter.addWidget(editor_scroll)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 4)

    def _connect_signals(self) -> None:
        self.search.textChanged.connect(self._apply_filter)  # type: ignore[attr-defined]
        self.table.currentCellChanged.connect(self._on_current_row_changed)  # type: ignore[attr-defined]
        self.table.itemSelectionChanged.connect(self._sync_bulk_state)  # type: ignore[attr-defined]
        self.liquid_editor.changed.connect(self._on_editor_changed)
        self.gas_editor.changed.connect(self._on_editor_changed)
        self.liquid_editor.volume_changed.connect(self._on_liquid_volume_changed)
        self.auto_headspace_switch.checkedChanged.connect(  # type: ignore[attr-defined]
            self._on_auto_headspace_changed
        )
        self.bulk_button.clicked.connect(self._apply_active_to_selection)  # type: ignore[attr-defined]
        self.apply_button.clicked.connect(self.apply_changes)  # type: ignore[attr-defined]
        self.discard_button.clicked.connect(self.discard_changes)  # type: ignore[attr-defined]

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._ensure_ui()
        self.sync(force=False)

    def _ensure_ui(self) -> None:
        if self._ui_ready:
            return
        self._setup_ui()
        self._connect_signals()
        self._ui_ready = True
        self._loading = True
        self._rebuild_table()
        self._restore_selection([], self._active_id)
        self._loading = False
        self._load_active_entry()
        self._refresh_actions()

    def sync(self, force: bool = False) -> None:
        """Merge live component inventories into the workspace draft."""

        if self._ui_ready and not force:
            self._save_editor_to_active()
        old_entries = {} if force else dict(self._entry_by_id)
        selected_ids = self._selected_ids() if self._ui_ready else []
        active_id = self._active_id

        entries: list[_InventoryEntry] = []
        for component_name, manager in self._component_provider():
            component_data = manager.inf
            ensure_air_defaults(component_data)
            for inventory_key, inventory in getattr(
                component_data,
                "internal_inventories",
                {},
            ).items():
                identity = (id(manager), str(inventory_key))
                previous = old_entries.get(identity)
                if previous is None:
                    draft = deepcopy(inventory)
                    auto_headspace = self._default_auto_headspace(
                        component_data,
                        draft,
                    )
                else:
                    draft = previous.draft_inventory
                    auto_headspace = previous.auto_headspace
                entries.append(
                    _InventoryEntry(
                        component_name=str(component_name),
                        inventory_key=str(inventory_key),
                        manager=manager,
                        component_data=component_data,
                        live_inventory=inventory,
                        draft_inventory=draft,
                        auto_headspace=auto_headspace,
                    )
                )

        self._entries = entries
        self._entry_by_id = {entry.identity: entry for entry in entries}
        if not self._ui_ready:
            if active_id not in self._entry_by_id:
                self._active_id = entries[0].identity if entries else None
            if force:
                self._dirty = False
            return
        self._loading = True
        self._rebuild_table()
        self._restore_selection(selected_ids, active_id)
        self._loading = False

        if force:
            self._dirty = False
        self._load_active_entry()
        self._refresh_actions()

    def sync_compounds(self) -> None:
        if not self._ui_ready:
            return
        self.liquid_editor.refresh_compounds()
        self.gas_editor.refresh_compounds()
        self._rebuild_table(preserve_selection=True)

    def draft_uses_compound(self, name: str) -> bool:
        """Return whether the current draft references a compound."""

        if self._ui_ready:
            self._save_editor_to_active()
        return any(
            name in entry.draft_inventory.liq_content.initial_species
            or name in entry.draft_inventory.gas_content.initial_species
            for entry in self._entries
        )

    def apply_changes(self) -> bool:
        self._save_editor_to_active()
        invalid = self._first_invalid_entry()
        if invalid is not None:
            self._focus_entry(invalid)
            total = self._total_volume_m3(invalid)
            capacity = invalid.capacity_m3
            assert capacity is not None
            self._show_error(
                "Inventory exceeds capacity",
                (
                    f"{invalid.component_name} / {invalid.inventory_key} uses "
                    f"{_format_volume(total)} of {_format_volume(capacity)}."
                ),
            )
            return False

        changed_managers: dict[int, ComponentManager] = {}
        for entry in self._entries:
            if entry.live_inventory == entry.draft_inventory:
                continue
            _copy_content(
                entry.live_inventory.liq_content,  # type: ignore[attr-defined]
                entry.draft_inventory.liq_content,  # type: ignore[attr-defined]
            )
            _copy_content(
                entry.live_inventory.gas_content,  # type: ignore[attr-defined]
                entry.draft_inventory.gas_content,  # type: ignore[attr-defined]
            )
            ensure_air_defaults(entry.component_data)
            changed_managers[id(entry.manager)] = entry.manager

        for manager in changed_managers.values():
            manager.graph.sync_visuals()

        self.sync(force=True)
        self._show_success(
            "Initial inventory updated",
            "Use the project Save action to persist these values to disk.",
        )
        return True

    def discard_changes(self) -> None:
        self.sync(force=True)

    def visible_inventory_names(self) -> list[str]:
        if not self._ui_ready:
            return [
                f"{entry.component_name} / {entry.inventory_key}"
                for entry in self._entries
            ]
        return [
            f"{entry.component_name} / {entry.inventory_key}"
            for row, entry in enumerate(self._entries)
            if not self.table.isRowHidden(row)
        ]

    def selected_inventory_ids(self) -> list[InventoryId]:
        return self._selected_ids()

    def _rebuild_table(self, preserve_selection: bool = False) -> None:
        selected_ids = self._selected_ids() if preserve_selection else []
        active_id = self._active_id
        self.table.blockSignals(True)
        self.table.setRowCount(len(self._entries))
        self._row_by_id = {}
        for row, entry in enumerate(self._entries):
            self._row_by_id[entry.identity] = row
            liquid = entry.draft_inventory.liq_content  # type: ignore[attr-defined]
            gas = entry.draft_inventory.gas_content  # type: ignore[attr-defined]
            capacity = entry.capacity_m3
            values = (
                entry.component_name,
                entry.inventory_key,
                _format_volume(float(liquid.volume)),
                _format_volume(float(gas.volume)),
                _format_volume(capacity) if capacity is not None else "Not limited",
                self._composition_summary(entry),
                self._entry_status(entry),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.UserRole, entry.identity)  # type: ignore[attr-defined]
                if column == 6 and self._is_over_capacity(entry):
                    item.setForeground(QColor("#dc2626"))
                self.table.setItem(row, column, item)
        self.table.blockSignals(False)
        self.empty_overview_label.setVisible(not self._entries)
        self._apply_filter(self.search.text())
        if preserve_selection:
            self._restore_selection(selected_ids, active_id)

    def _restore_selection(
        self,
        selected_ids: list[InventoryId],
        active_id: InventoryId | None,
    ) -> None:
        row = self._row_by_id.get(active_id) if active_id is not None else None
        if row is None and self._entries:
            row = 0
        if row is not None:
            self.table.setCurrentCell(row, 0)
            self._active_id = self._entries[row].identity
        else:
            self._active_id = None
        self.table.clearSelection()
        selection_model = self.table.selectionModel()
        if selection_model is not None:
            identities = selected_ids or ([self._active_id] if self._active_id else [])
            if self._active_id is not None and self._active_id not in identities:
                identities.append(self._active_id)
            for identity in identities:
                selected_row = self._row_by_id.get(identity)
                if selected_row is not None:
                    selection_model.select(
                        self.table.model().index(selected_row, 0),
                        QItemSelectionModel.Select  # type: ignore[attr-defined]
                        | QItemSelectionModel.Rows,  # type: ignore[attr-defined]
                    )

    def _on_current_row_changed(
        self,
        current_row: int,
        _current_column: int,
        _previous_row: int,
        _previous_column: int,
    ) -> None:
        if self._loading:
            return
        self._save_editor_to_active()
        if 0 <= current_row < len(self._entries):
            self._active_id = self._entries[current_row].identity
        else:
            self._active_id = None
        self._load_active_entry()

    def _active_entry(self) -> _InventoryEntry | None:
        if self._active_id is None:
            return None
        return self._entry_by_id.get(self._active_id)

    def _load_active_entry(self) -> None:
        entry = self._active_entry()
        self._loading = True
        has_entry = entry is not None
        self.editor_content.setEnabled(has_entry)
        if entry is None:
            self.editor_title.setText("Select an inventory")
            self.editor_subtitle.setText("")
            self.capacity_text.setText("")
            self.capacity_detail.setText("")
            self.capacity_bar.set_values(0.0, 0.0, None)
            self._loading = False
            return

        self.editor_title.setText(f"{entry.component_name} / {entry.inventory_key}")
        self.editor_subtitle.setText("Initial contents")
        self.liquid_editor.load(entry.draft_inventory.liq_content)  # type: ignore[attr-defined]
        self.gas_editor.load(entry.draft_inventory.gas_content)  # type: ignore[attr-defined]
        self.auto_headspace_switch.setEnabled(entry.capacity_m3 is not None)
        self.auto_headspace_switch.setChecked(entry.auto_headspace)
        self.gas_editor.set_volume_read_only(entry.auto_headspace)
        self._refresh_capacity(entry)
        self._loading = False

    def _save_editor_to_active(self) -> None:
        if self._loading:
            return
        entry = self._active_entry()
        if entry is None:
            return
        self.liquid_editor.save(entry.draft_inventory.liq_content)  # type: ignore[attr-defined]
        self.gas_editor.save(entry.draft_inventory.gas_content)  # type: ignore[attr-defined]

    def _on_editor_changed(self) -> None:
        if self._loading:
            return
        self._save_editor_to_active()
        self._dirty = True
        entry = self._active_entry()
        if entry is not None:
            self._refresh_capacity(entry)
        self._rebuild_table(preserve_selection=True)
        self._refresh_actions()

    def _on_liquid_volume_changed(self, _volume_m3: float) -> None:
        if self._loading:
            return
        entry = self._active_entry()
        if entry is None or not entry.auto_headspace:
            return
        self._save_editor_to_active()
        self._balance_headspace(entry)
        self._loading = True
        self.gas_editor.load(entry.draft_inventory.gas_content)  # type: ignore[attr-defined]
        self.gas_editor.set_volume_read_only(True)
        self._loading = False

    def _on_auto_headspace_changed(self, checked: bool) -> None:
        if self._loading:
            return
        entry = self._active_entry()
        if entry is None or entry.capacity_m3 is None:
            return
        self._save_editor_to_active()
        entry.auto_headspace = checked
        if checked:
            self._balance_headspace(entry)
            self._loading = True
            self.gas_editor.load(entry.draft_inventory.gas_content)  # type: ignore[attr-defined]
            self._loading = False
        self.gas_editor.set_volume_read_only(checked)
        self._dirty = True
        self._refresh_capacity(entry)
        self._rebuild_table(preserve_selection=True)
        self._refresh_actions()

    def _balance_headspace(self, entry: _InventoryEntry) -> None:
        capacity = entry.capacity_m3
        if capacity is None:
            return
        self._balance_inventory_headspace(entry.draft_inventory, capacity)

    @staticmethod
    def _balance_inventory_headspace(
        inventory: InventoryNode,
        capacity: float,
    ) -> None:
        liquid = inventory.liq_content  # type: ignore[attr-defined]
        gas = inventory.gas_content  # type: ignore[attr-defined]
        gas.volume = max(0.0, capacity - float(liquid.volume))
        species = dict(gas.initial_species)
        if not species or set(species) == {"air"}:
            if gas.volume <= 0.0:
                gas.initial_species = {}
                return
            air = COMPOUNDS["air"]
            molar_volume = float(
                air.molar_volume_gas(
                    gas.initial_temperature,
                    gas.initial_pressure,
                ).magnitude
            )
            gas.initial_species = {"air": gas.volume / molar_volume}

    def _refresh_capacity(self, entry: _InventoryEntry) -> None:
        liquid = float(entry.draft_inventory.liq_content.volume)  # type: ignore[attr-defined]
        gas = float(entry.draft_inventory.gas_content.volume)  # type: ignore[attr-defined]
        capacity = entry.capacity_m3
        self.capacity_bar.set_values(liquid, gas, capacity)
        if capacity is None:
            self.capacity_text.setText("Not limited")
            self.capacity_detail.setText(
                f"Liquid {_format_volume(liquid)} · Gas {_format_volume(gas)}"
            )
            self.capacity_detail.setStyleSheet("")
            return
        total = liquid + gas
        remaining = capacity - total
        self.capacity_text.setText(_format_volume(capacity))
        if remaining < -_CAPACITY_TOLERANCE_M3:
            self.capacity_detail.setText(
                f"Over capacity by {_format_volume(-remaining)}"
            )
            self.capacity_detail.setStyleSheet("color: #dc2626;")
        else:
            self.capacity_detail.setText(
                f"Liquid {_format_volume(liquid)} · Gas {_format_volume(gas)} · "
                f"Remaining {_format_volume(max(0.0, remaining))}"
            )
            self.capacity_detail.setStyleSheet("")

    def _apply_filter(self, text: str) -> None:
        query = text.strip().casefold()
        for row, entry in enumerate(self._entries):
            haystack = " ".join(
                (
                    entry.component_name,
                    entry.inventory_key,
                    self._composition_summary(entry),
                )
            ).casefold()
            self.table.setRowHidden(row, bool(query and query not in haystack))

    def _selected_ids(self) -> list[InventoryId]:
        selection_model = self.table.selectionModel()
        if selection_model is None:
            return []
        identities: list[InventoryId] = []
        for index in selection_model.selectedRows():
            if 0 <= index.row() < len(self._entries):
                identities.append(self._entries[index.row()].identity)
        return identities

    def _selected_entries(self) -> list[_InventoryEntry]:
        return [
            entry
            for identity in self._selected_ids()
            if (entry := self._entry_by_id.get(identity)) is not None
        ]

    def _sync_bulk_state(self) -> None:
        self.bulk_button.setEnabled(
            self._active_entry() is not None and len(self._selected_ids()) > 1
        )

    def _apply_active_to_selection(self) -> None:
        source = self._active_entry()
        targets = (
            [
                entry
                for entry in self._selected_entries()
                if entry.identity != source.identity
            ]
            if source is not None
            else []
        )
        if source is None or not targets:
            return
        self._save_editor_to_active()
        scope = self.bulk_scope_combo.currentData()

        candidates: dict[InventoryId, InventoryNode] = {}
        candidate_auto_modes: dict[InventoryId, bool] = {}
        for target in targets:
            candidate = deepcopy(target.draft_inventory)
            if scope in ("Both phases", "Liquid only"):
                _copy_content(
                    candidate.liq_content,  # type: ignore[attr-defined]
                    source.draft_inventory.liq_content,  # type: ignore[attr-defined]
                )
            if scope in ("Both phases", "Gas only"):
                _copy_content(
                    candidate.gas_content,  # type: ignore[attr-defined]
                    source.draft_inventory.gas_content,  # type: ignore[attr-defined]
                )
            capacity = target.capacity_m3
            candidate_auto = target.auto_headspace
            if scope == "Both phases" and capacity is not None:
                candidate_auto = source.auto_headspace
            if (
                candidate_auto
                and capacity is not None
                and scope in ("Both phases", "Liquid only")
            ):
                self._balance_inventory_headspace(candidate, capacity)
            total = float(candidate.liq_content.volume) + float(  # type: ignore[attr-defined]
                candidate.gas_content.volume  # type: ignore[attr-defined]
            )
            if capacity is not None and total > capacity + _CAPACITY_TOLERANCE_M3:
                self._focus_entry(target)
                self._show_error(
                    "Bulk edit exceeds capacity",
                    (
                        f"{target.component_name} / {target.inventory_key} would use "
                        f"{_format_volume(total)} of {_format_volume(capacity)}."
                    ),
                )
                return
            candidates[target.identity] = candidate
            candidate_auto_modes[target.identity] = candidate_auto

        for target in targets:
            target.draft_inventory = candidates[target.identity]
            target.auto_headspace = candidate_auto_modes[target.identity]
        self._dirty = True
        self._rebuild_table(preserve_selection=True)
        self._refresh_actions()
        self._show_success(
            "Draft inventories updated",
            f"Applied {scope.lower()} to {len(targets)} selected inventories.",
        )

    def _refresh_actions(self) -> None:
        invalid = self._first_invalid_entry()
        self.apply_button.setEnabled(self._dirty and invalid is None)
        self.discard_button.setEnabled(self._dirty)
        self._sync_bulk_state()

    def _first_invalid_entry(self) -> _InventoryEntry | None:
        return next(
            (entry for entry in self._entries if self._is_over_capacity(entry)),
            None,
        )

    @staticmethod
    def _total_volume_m3(entry: _InventoryEntry) -> float:
        return float(entry.draft_inventory.liq_content.volume) + float(  # type: ignore[attr-defined]
            entry.draft_inventory.gas_content.volume  # type: ignore[attr-defined]
        )

    def _is_over_capacity(self, entry: _InventoryEntry) -> bool:
        capacity = entry.capacity_m3
        return (
            capacity is not None
            and self._total_volume_m3(entry) > capacity + _CAPACITY_TOLERANCE_M3
        )

    def _entry_status(self, entry: _InventoryEntry) -> str:
        if self._is_over_capacity(entry):
            return "Over capacity"
        liquid = entry.draft_inventory.liq_content  # type: ignore[attr-defined]
        gas = entry.draft_inventory.gas_content  # type: ignore[attr-defined]
        if float(liquid.volume) <= 0.0 and set(getattr(gas, "initial_species", {})) <= {
            "air"
        }:
            return "Air only"
        return "Configured"

    @staticmethod
    def _composition_summary(entry: _InventoryEntry) -> str:
        liquid_names = list(
            entry.draft_inventory.liq_content.initial_species  # type: ignore[attr-defined]
        )
        gas_names = list(
            entry.draft_inventory.gas_content.initial_species  # type: ignore[attr-defined]
        )
        parts = []
        if liquid_names:
            parts.append("L: " + ", ".join(liquid_names))
        if gas_names:
            parts.append("G: " + ", ".join(gas_names))
        return " · ".join(parts) if parts else "Empty"

    @staticmethod
    def _default_auto_headspace(component_data: object, inventory: object) -> bool:
        capacity = inventory_capacity_m3(component_data)
        if capacity is None:
            return False
        gas = inventory.gas_content  # type: ignore[attr-defined]
        species = set(getattr(gas, "initial_species", {}))
        return species <= {"air"}

    def _focus_entry(self, entry: _InventoryEntry) -> None:
        row = self._row_by_id.get(entry.identity)
        if row is None:
            return
        self.table.setCurrentCell(row, 0)
        self.table.selectRow(row)
        self._active_id = entry.identity
        self._load_active_entry()

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

    def _show_success(self, title: str, content: str) -> None:
        InfoBar.success(
            title=title,
            content=content,
            orient=Qt.Horizontal,  # type: ignore[attr-defined]
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=2500,
            parent=self.window(),
        )
