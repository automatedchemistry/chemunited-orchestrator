from __future__ import annotations

from pydantic.fields import FieldInfo
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    ComboBox,
    FluentIcon,
    LineEdit,
    PrimaryPushButton,
    PushButton,
    SmoothScrollArea,
    TransparentToolButton,
    isDarkTheme,
)
from qframelesswindow import FramelessDialog

from chemunited.shared.widgets.base_mode_editor.cards.base_card import BaseFieldCard
from chemunited.shared.widgets.base_mode_editor.cards.bool_card import BoolFieldCard
from chemunited.shared.widgets.base_mode_editor.cards.float_card import FloatFieldCard
from chemunited.shared.widgets.base_mode_editor.cards.int_card import IntFieldCard
from chemunited.shared.widgets.base_mode_editor.cards.str_card import StrFieldCard

ParameterValue = str | int | float | bool

_CARD_TYPES: dict[str, tuple[type, type[BaseFieldCard]]] = {
    "str": (str, StrFieldCard),
    "int": (int, IntFieldCard),
    "float": (float, FloatFieldCard),
    "bool": (bool, BoolFieldCard),
}


def _type_name_for(value: ParameterValue) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    return "str"


class _ParameterRow(QWidget):
    """Key name + type picker + a typed value card, rebuilt whenever the
    key or the chosen type changes."""

    removed = pyqtSignal(object)

    def __init__(
        self,
        key: str = "",
        value: ParameterValue = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._card: BaseFieldCard | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)

        self._key_edit = LineEdit(self)
        self._key_edit.setPlaceholderText("Parameter name")
        self._key_edit.setText(key)
        self._key_edit.editingFinished.connect(self._rebuild_card)
        header.addWidget(self._key_edit, stretch=1)

        self._type_combo = ComboBox(self)
        self._type_combo.addItems(list(_CARD_TYPES))
        self._type_combo.setCurrentText(_type_name_for(value))
        self._type_combo.setFixedWidth(90)
        self._type_combo.currentTextChanged.connect(self._rebuild_card)
        header.addWidget(self._type_combo)

        remove_button = TransparentToolButton(FluentIcon.DELETE, self)
        remove_button.setToolTip("Remove parameter")
        remove_button.clicked.connect(lambda: self.removed.emit(self))
        header.addWidget(remove_button)

        outer.addLayout(header)

        self._card_slot = QVBoxLayout()
        self._card_slot.setContentsMargins(0, 0, 0, 0)
        outer.addLayout(self._card_slot)

        self._build_card(value)

    def _rebuild_card(self, *_args: object) -> None:
        current_value = self._card.get_value() if self._card is not None else None
        self._build_card(current_value)

    def _build_card(self, value: ParameterValue | None) -> None:
        if self._card is not None:
            self._card_slot.removeWidget(self._card)
            self._card.setParent(None)
            self._card.deleteLater()
            self._card = None

        annotation, card_cls = _CARD_TYPES[self._type_combo.currentText()]
        field_info = FieldInfo(annotation=annotation, default=annotation())
        card = card_cls(self._key_edit.text().strip() or "value", field_info, self)
        if value is not None:
            try:
                card.set_value(value)
            except (TypeError, ValueError):
                pass
        self._card = card
        self._card_slot.addWidget(card)

    def key(self) -> str:
        return self._key_edit.text().strip()

    def value(self) -> ParameterValue:
        assert self._card is not None
        return self._card.get_value()

    def validate(self) -> bool:
        assert self._card is not None
        return self._card.validate()


class NodeParametersDialog(FramelessDialog):
    """Right-click "Edit parameters" dialog for a single workflow block.

    Builds the ``dict[str, str | int | float | bool]`` that ends up on
    ``BlockData.parameters`` / ``ctx.node_config.parameters`` at execution time.
    """

    parameters_saved = pyqtSignal(str, dict)

    def __init__(
        self,
        node_id: str,
        parameters: dict[str, ParameterValue] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._node_id = node_id
        self._rows: list[_ParameterRow] = []

        self.setObjectName("nodeParametersDialog")
        self.setWindowTitle(f"Edit parameters — {node_id}")
        self.setMinimumSize(520, 420)
        self.resize(560, 480)

        self._build_ui()
        self._apply_styles()

        for key, value in (parameters or {}).items():
            self._add_row(key, value)
        if not self._rows:
            self._add_row()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, self.titleBar.height() + 16, 16, 16)
        layout.setSpacing(12)

        self._scroll_area = SmoothScrollArea(self)
        self._scroll_area.setWidgetResizable(True)
        self._scroll_content = QWidget(self._scroll_area)
        self._rows_layout = QVBoxLayout(self._scroll_content)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(10)
        self._rows_layout.addStretch()
        self._scroll_area.setWidget(self._scroll_content)
        layout.addWidget(self._scroll_area, stretch=1)

        add_button = PushButton("Add parameter", self)
        add_button.setIcon(FluentIcon.ADD.icon())
        add_button.clicked.connect(lambda: self._add_row())
        layout.addWidget(add_button)

        layout.addLayout(self._build_footer())

    def _build_footer(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addStretch()

        cancel_button = PushButton("cancel", self)
        cancel_button.setMinimumWidth(92)
        cancel_button.clicked.connect(self.reject)
        layout.addWidget(cancel_button)

        save_button = PrimaryPushButton("save", self)
        save_button.setMinimumWidth(92)
        save_button.clicked.connect(self._on_save)
        layout.addWidget(save_button)

        return layout

    def _add_row(self, key: str = "", value: ParameterValue = "") -> None:
        row = _ParameterRow(key, value, self._scroll_content)
        row.removed.connect(self._remove_row)
        self._rows.append(row)
        self._rows_layout.insertWidget(self._rows_layout.count() - 1, row)

    def _remove_row(self, row: _ParameterRow) -> None:
        self._rows.remove(row)
        self._rows_layout.removeWidget(row)
        row.deleteLater()

    def _on_save(self) -> None:
        parameters: dict[str, ParameterValue] = {}
        for row in self._rows:
            if not row.validate():
                return
            key = row.key()
            if not key:
                continue
            parameters[key] = row.value()

        self.parameters_saved.emit(self._node_id, parameters)
        self.accept()

    def _apply_styles(self) -> None:
        panel_border = (
            "rgba(255, 255, 255, 0.12)" if isDarkTheme() else "rgba(0, 0, 0, 0.12)"
        )
        dialog_fill = "#2f2f2f" if isDarkTheme() else "#f7f7f7"

        self.setStyleSheet(
            f"""
            QDialog#nodeParametersDialog {{
                background-color: {dialog_fill};
                border: 1px solid {panel_border};
                border-radius: 10px;
            }}
            """
        )
