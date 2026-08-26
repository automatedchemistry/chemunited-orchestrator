from __future__ import annotations

from chemunited_workflow.enums import NodeState
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWidgets import QHBoxLayout, QSizePolicy, QStackedWidget, QWidget
from qfluentwidgets import (
    Action,
    BodyLabel,
    FluentIcon,
    LineEdit,
    RoundMenu,
    ToolButton,
)

QT_KEY_ESCAPE = getattr(Qt, "Key_Escape")
QT_NO_PEN = getattr(Qt, "NoPen")

_STATUS_DEFAULT_COLOR = QColor(120, 120, 120)
_STATUS_RUNNING_COLOR = QColor(38, 166, 91)
_STATUS_RUNNING_DIM_COLOR = QColor(38, 166, 91, 80)
_STATUS_COMPLETED_COLOR = QColor(38, 166, 91)
_STATUS_FAILED_COLOR = QColor(220, 53, 69)
_STATIC_STATES = {
    NodeState.NOT_VISITED,
    NodeState.WAITING,
    NodeState.INACTIVE,
}


class _StatusCircle(QWidget):
    """Small state indicator for a workflow process row."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(12, 12)
        self._state = NodeState.NOT_VISITED
        self._color = QColor(_STATUS_DEFAULT_COLOR)
        self._blink_on = True
        self._blink_timer = QTimer(self)
        self._blink_timer.setInterval(500)
        self._blink_timer.timeout.connect(self._toggle_running_blink)  # type: ignore[attr-defined]

    def set_status(self, status) -> None:
        state = _coerce_node_state(status)
        if state is None:
            state = NodeState.NOT_VISITED

        self._state = state
        self.setToolTip(state.value)
        if state == NodeState.RUNNING:
            self._blink_on = True
            self._set_color(_STATUS_RUNNING_COLOR)
            if not self._blink_timer.isActive():
                self._blink_timer.start()
            return

        if self._blink_timer.isActive():
            self._blink_timer.stop()

        if state in _STATIC_STATES:
            self._set_color(_STATUS_DEFAULT_COLOR)
        elif state == NodeState.COMPLETED:
            self._set_color(_STATUS_COMPLETED_COLOR)
        elif state == NodeState.FAILED:
            self._set_color(_STATUS_FAILED_COLOR)
        else:
            self._set_color(_STATUS_DEFAULT_COLOR)

    def _toggle_running_blink(self) -> None:
        self._blink_on = not self._blink_on
        self._set_color(
            _STATUS_RUNNING_COLOR if self._blink_on else _STATUS_RUNNING_DIM_COLOR
        )

    def _set_color(self, color: QColor) -> None:
        self._color = QColor(color)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(self._color)
        painter.setPen(QT_NO_PEN)
        painter.drawEllipse(1, 1, 10, 10)


class _EditLineEdit(LineEdit):
    """LineEdit with dedicated signals for Escape key and focus loss."""

    escape_pressed = pyqtSignal()
    focus_lost = pyqtSignal()

    def keyPressEvent(self, event) -> None:
        if event.key() == QT_KEY_ESCAPE:
            self.escape_pressed.emit()  # type: ignore[attr-defined]
        else:
            super().keyPressEvent(event)

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self.focus_lost.emit()  # type: ignore[attr-defined]


class ProcessItem(QWidget):
    """Passive, uniform row widget. Emits signals only — owns no logic."""

    option_triggered = pyqtSignal(str, str)  # (option_name, process_name)
    rename_requested = pyqtSignal(str, str)  # (current_name, proposed_name)
    edit_started = pyqtSignal(str)  # (process_name)

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

        self._edit.returnPressed.connect(lambda: self._exit_edit_mode(confirm=True))  # type: ignore
        self._edit.escape_pressed.connect(lambda: self._exit_edit_mode(confirm=False))  # type: ignore
        self._edit.focus_lost.connect(lambda: self._exit_edit_mode(confirm=True))  # type: ignore

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
            self._menu_button.clicked.connect(self._show_menu)  # type: ignore

        option_name = name

        def _on_triggered() -> None:
            self.option_triggered.emit(option_name, self._name)  # type: ignore

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
            self._menu_button.clicked.connect(self._show_menu)  # type: ignore
        action = Action(FluentIcon.EDIT, "Rename")
        action.setToolTip("Rename this process")
        action.triggered.connect(self._enter_edit_mode)
        self._menu.addAction(action)
        self._menu_button.setVisible(True)

    def set_name(self, name: str) -> None:
        self._name = name
        self._name_label.setText(name)

    def set_status(self, status) -> None:
        self._status.set_status(status)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _enter_edit_mode(self) -> None:
        if self._editing:
            return
        self._editing = True
        self.edit_started.emit(self._name)  # type: ignore[attr-defined]
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
                self.rename_requested.emit(self._name, text)  # type: ignore[attr-defined]

    def _show_menu(self) -> None:
        if self._menu is not None:
            pos = self._menu_button.mapToGlobal(self._menu_button.rect().bottomLeft())
            self._menu.exec(pos)


def _coerce_node_state(status) -> NodeState | None:
    if isinstance(status, NodeState):
        return status
    if status is None:
        return None

    text = str(status).strip()
    if not text:
        return None
    if "." in text:
        text = text.rsplit(".", 1)[-1]
    text = text.upper()
    try:
        return NodeState(text)
    except ValueError:
        try:
            return NodeState[text]
        except KeyError:
            return None
