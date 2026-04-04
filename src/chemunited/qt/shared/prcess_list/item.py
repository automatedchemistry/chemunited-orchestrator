from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWidgets import QHBoxLayout, QSizePolicy, QStackedWidget, QWidget
from qfluentwidgets import Action, BodyLabel, FluentIcon, LineEdit, RoundMenu, ToolButton
from loguru import logger


class _StatusCircle(QWidget):
    """Circle placeholder — replace with real status widget later."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(12, 12)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(120, 120, 120))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(1, 1, 10, 10)


class _EditLineEdit(LineEdit):
    """LineEdit with dedicated signals for Escape key and focus loss."""

    escape_pressed = pyqtSignal()
    focus_lost = pyqtSignal()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.escape_pressed.emit()
        else:
            super().keyPressEvent(event)

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self.focus_lost.emit()


class ProcessItem(QWidget):
    """Passive, uniform row widget. Emits signals only — owns no logic."""

    option_triggered = pyqtSignal(str, str)  # (option_name, process_name)
    rename_requested = pyqtSignal(str, str)  # (current_name, proposed_name)
    edit_started = pyqtSignal(str)           # (process_name)

    def __init__(self, name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._name: str = name
        self._enable_rename: bool = False
        self._editing: bool = False
        self._menu: RoundMenu | None = None
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._stack = QStackedWidget(self)
        outer.addWidget(self._stack)

        # Page 0 — display mode
        display_page = QWidget()
        display_layout = QHBoxLayout(display_page)
        display_layout.setContentsMargins(8, 4, 4, 4)
        display_layout.setSpacing(6)

        self._status = _StatusCircle(display_page)
        display_layout.addWidget(self._status)

        self._name_label = BodyLabel(self._name, display_page)
        self._name_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        display_layout.addWidget(self._name_label)

        self._menu_button = ToolButton(FluentIcon.MORE, display_page)
        self._menu_button.setVisible(False)
        display_layout.addWidget(self._menu_button)

        self._stack.addWidget(display_page)

        # Page 1 — edit mode
        edit_page = QWidget()
        edit_layout = QHBoxLayout(edit_page)
        edit_layout.setContentsMargins(8, 4, 4, 4)

        self._edit = _EditLineEdit(edit_page)
        edit_layout.addWidget(self._edit)

        self._edit.returnPressed.connect(lambda: self._exit_edit_mode(confirm=True))
        self._edit.escape_pressed.connect(lambda: self._exit_edit_mode(confirm=False))
        self._edit.focus_lost.connect(lambda: self._exit_edit_mode(confirm=True))

        self._stack.addWidget(edit_page)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return self._name

    def add_option(self, name: str, icon, tip: str) -> None:
        """Add a menu option. Action only emits option_triggered — no callable."""
        if self._menu is None:
            self._menu = RoundMenu(parent=self)
            self._menu_button.clicked.connect(self._show_menu)

        option_name = name

        def _on_triggered() -> None:
            self.option_triggered.emit(option_name, self._name)

        action = Action(icon, option_name)
        action.setToolTip(tip)
        action.triggered.connect(_on_triggered)
        self._menu.addAction(action)
        self._menu_button.setVisible(True)

    def enable_rename(self) -> None:
        """Enable inline rename via the context menu.

        Rename is a purely visual/internal operation — the action connects
        directly to _enter_edit_mode without going through option_triggered,
        so the list dispatch table is never involved.
        """
        self._enable_rename = True
        if self._menu is None:
            self._menu = RoundMenu(parent=self)
            self._menu_button.clicked.connect(self._show_menu)
        action = Action(FluentIcon.EDIT, "Rename")
        action.setToolTip("Rename this process")
        action.triggered.connect(self._enter_edit_mode)
        self._menu.addAction(action)
        self._menu_button.setVisible(True)

    def set_name(self, name: str) -> None:
        self._name = name
        self._name_label.setText(name)

    def set_status(self, status) -> None:
        pass  # placeholder — ready for a future enum

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _enter_edit_mode(self) -> None:
        if self._editing:
            return
        self._editing = True
        self.edit_started.emit(self._name)
        self._edit.setText(self._name)
        self._edit.selectAll()
        self._stack.setCurrentIndex(1)
        self._edit.setFocus()

    def _exit_edit_mode(self, confirm: bool) -> None:
        if not self._editing:
            return
        self._editing = False
        self._stack.setCurrentIndex(0)
        if confirm:
            text = self._edit.text().strip()
            if text and text != self._name:
                self.rename_requested.emit(self._name, text)

    def _show_menu(self) -> None:
        if self._menu is not None:
            pos = self._menu_button.mapToGlobal(self._menu_button.rect().bottomLeft())
            self._menu.exec(pos)
