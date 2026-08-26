from __future__ import annotations

from chemunited_workflow.enums import NodeState
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWidgets import QWidget

_STATUS_WAITING_COLOR = QColor(229, 171, 0)
_STATUS_RUNNING_COLOR = QColor(38, 166, 91)
_STATUS_COMPLETED_COLOR = QColor(38, 166, 91)
_STATUS_FAILED_COLOR = QColor(220, 53, 69)
_BAR_HEIGHT = 6


class WorkflowStatusBar(QWidget):
    """Self-painted workflow node status indicator backed by NodeState."""

    def __init__(self, width: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = NodeState.NOT_VISITED
        self._value = 0
        self._color = _STATUS_COMPLETED_COLOR
        self._animation_offset = 0
        self.setFixedSize(width, _BAR_HEIGHT)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._animation_timer = QTimer(self)
        self._animation_timer.setInterval(35)
        self._animation_timer.timeout.connect(self._advance_animation)

        self.set_status(NodeState.NOT_VISITED)

    def set_status(self, status) -> bool:
        state = _coerce_node_state(status) or NodeState.NOT_VISITED
        self._state = state
        self.setToolTip(state.value)

        if state == NodeState.RUNNING:
            self._value = 100
            self._color = _STATUS_RUNNING_COLOR
            if not self._animation_timer.isActive():
                self._animation_timer.start()
            self.update()
            return True

        self._animation_timer.stop()
        self._animation_offset = 0

        if state in {NodeState.NOT_VISITED, NodeState.INACTIVE}:
            self._value = 0
            self._color = _STATUS_COMPLETED_COLOR
            self.update()
            return False
        if state == NodeState.WAITING:
            self._set_static_value(_STATUS_WAITING_COLOR, 100)
            return True
        if state == NodeState.COMPLETED:
            self._set_static_value(_STATUS_COMPLETED_COLOR, 100)
            return True
        if state == NodeState.FAILED:
            self._set_static_value(_STATUS_FAILED_COLOR, 100)
            return True

        self._value = 0
        self._color = _STATUS_COMPLETED_COLOR
        self.update()
        return False

    def is_running(self) -> bool:
        return self._animation_timer.isActive()

    def value(self) -> int:
        return self._value

    def bar_color(self) -> QColor:
        return QColor(self._color)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self._value <= 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        if self._state == NodeState.RUNNING:
            self._paint_running(painter)
            return

        painter.setBrush(self._color)
        painter.drawRoundedRect(self.rect(), 3, 3)

    def _paint_running(self, painter: QPainter) -> None:
        width = self.width()
        height = self.height()
        track = QColor(self._color)
        track.setAlpha(45)
        painter.setBrush(track)
        painter.drawRoundedRect(self.rect(), 3, 3)

        segment_width = min(max(width // 3, 36), width)
        travel = width + segment_width
        left = (self._animation_offset % travel) - segment_width
        painter.setBrush(self._color)
        painter.drawRoundedRect(left, 0, segment_width, height, 3, 3)

    def _set_static_value(self, color: QColor, value: int) -> None:
        self._color = QColor(color)
        self._value = value
        self.update()

    def _advance_animation(self) -> None:
        self._animation_offset += 8
        self.update()


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
