from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import CardWidget, CaptionLabel, StrongBodyLabel


class BaseFieldCard(CardWidget):
    """Abstract base for all typed field cards rendered inside BaseModeEditorWidget."""

    value_changed = pyqtSignal(object)

    def __init__(self, field_name: str, field_info, parent: QWidget | None = None):
        super().__init__(parent)
        self._field_name = field_name
        self._field_info = field_info
        self._touched = False  # True once validate() has been called at least once
        self._valid = False
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)

        # 1. title row
        title_row = QHBoxLayout()
        self._title_label = StrongBodyLabel(self._field_info.title or self._field_name)
        self._badge_label = CaptionLabel(self._type_badge())
        title_row.addWidget(self._title_label)
        title_row.addStretch()
        title_row.addWidget(self._badge_label)
        layout.addLayout(title_row)

        # 2. description (hidden when empty)
        # addWidget first so the label has a parent before setVisible(True) is
        # called — a parentless widget shown via setVisible(True) briefly becomes
        # a top-level HWND on Windows, causing a visible flash.
        desc = self._field_info.description or ""
        self._desc_label = CaptionLabel(desc)
        layout.addWidget(self._desc_label)
        self._desc_label.setVisible(bool(desc))

        # 3. input widget filled in by subclass
        self._input_widget = self._build_input()
        layout.addWidget(self._input_widget)

        # 4. error area (hidden until an error is set)
        self._error_label = CaptionLabel("")
        self._error_label.setVisible(False)
        layout.addWidget(self._error_label)

    # ------------------------------------------------------------------
    # Subclass interface
    # ------------------------------------------------------------------

    def _type_badge(self) -> str:
        raise NotImplementedError

    def _build_input(self) -> QWidget:
        raise NotImplementedError

    def get_value(self):
        raise NotImplementedError

    def set_value(self, value) -> None:
        raise NotImplementedError

    def validate(self) -> bool:
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Error helpers (called by subclasses)
    # ------------------------------------------------------------------

    def _set_error(self, message: str) -> None:
        if message:
            self._touched = True
            self._valid = False
            self._error_label.setText(message)
            self._error_label.setVisible(True)
            self._error_label.setStyleSheet("color: #c42b1c;")
        else:
            self._error_label.setVisible(False)
            self._error_label.setText("")
        self.update()

    def _clear_error(self) -> None:
        self._set_error("")

    def _mark_valid(self) -> None:
        self._touched = True
        self._valid = True
        self._clear_error()

    # ------------------------------------------------------------------
    # Left-border accent
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if not self._touched:
            return
        painter = QPainter(self)
        color = QColor("#0f7b0f") if self._valid else QColor("#c42b1c")
        painter.fillRect(0, 0, 3, self.height(), color)
