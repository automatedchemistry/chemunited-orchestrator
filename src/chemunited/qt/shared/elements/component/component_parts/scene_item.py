from typing import ClassVar
from PyQt5.QtCore import QRectF, QTimer, Qt, QPointF
from PyQt5.QtGui import QColor, QPen, QBrush, QPainterPath, QFont
from PyQt5.QtWidgets import QGraphicsObject
from qfluentwidgets import isDarkTheme


PATTERN_DIMENSION = 50

CONTOUR_DARK = "#3A3A3A"
SOLID_DARK = "#525252"
EVIDENCE_DARK = "#F9F9F9"

CONTOUR_DARK_BRIGHTER = "#6E6E6E"
SOLID_DARK_BRIGHTER = "#8A8A8A"

CONTOUR_LIGHT = "#BFC7D1"
SOLID_LIGHT = "#F4F7FB"
EVIDENCE_LIGHT = "#1F2937"

CONTOUR_LIGHT_DARKER = "#98A2B3"
SOLID_LIGHT_DARKER = "#D8E0EA"


class SceneItem(QGraphicsObject):

    theme_colors: ClassVar[dict[str, dict[str, QColor]]] = {
        "dark": {
            "contour": QColor(CONTOUR_DARK),
            "solid": QColor(SOLID_DARK),
            "gradient": QColor(SOLID_DARK_BRIGHTER),
            "evidence": QColor(EVIDENCE_DARK),
        },
        "light": {
            "contour": QColor(CONTOUR_LIGHT),
            "solid": QColor(SOLID_LIGHT),
            "gradient": QColor(SOLID_LIGHT_DARKER),
            "evidence": QColor(EVIDENCE_LIGHT),
        },
    }

    def __init__(
        self,
        width: int = PATTERN_DIMENSION,
        height: int | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.width = width
        self.height = height if height is not None else width

        self._counter: int = 0
        self._interval_animation: int = -1

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_timer)

    def boundingRect(self) -> QRectF:
        return QRectF(
            -self.width / 2,
            -self.height / 2,
            self.width,
            self.height,
        )

    @property
    def current_theme(self) -> str:
        return "dark" if isDarkTheme() else "light"

    @property
    def colors(self) -> dict[str, QColor]:
        return self.theme_colors[self.current_theme]

    def start_animation(self, fps: int = 60, frames: int = -1) -> None:
        self._interval_animation = frames
        self._counter = 0
        self._timer.start(int(1000 / fps))

    def stop_animation(self) -> None:
        self._timer.stop()
        self._counter = 0
        parent = self.parentItem()
        if parent is not None and hasattr(parent, "stop_animation"):
            parent.stop_animation()

    def _on_timer(self) -> None:
        self._counter += 1
        if self._interval_animation != -1 and self._counter >= self._interval_animation:
            self.stop_animation()
            return
        self.update()


class ConnectivityBadge(SceneItem):
    """
    WiFi-arc connectivity indicator.
    Shown only on electronic (device) components.

    Online  → green arcs + API address below
    Offline → red arcs + diagonal strike + API address below (muted)
    """

    COLOR_ONLINE:  QColor = QColor("#4CAF50")   # green
    COLOR_OFFLINE: QColor = QColor("#F44336")   # red
    COLOR_API_ON:  QColor = QColor("#4CAF50")
    COLOR_API_OFF: QColor = QColor("#888888")   # muted gray when offline

    def __init__(self, dimension: int = PATTERN_DIMENSION, parent=None):
        super().__init__(width=dimension, height=dimension, parent=parent)
        self.radius = dimension / 2
        self._status: bool = False
        self._api: str = ""

    # ── public API ────────────────────────────────────────────────

    def setStatus(self, online: bool, api: str = "") -> None:
        self._status = online
        self._api = api
        self.update()

    # ── painting ──────────────────────────────────────────────────

    def paint(self, painter, option, widget=None):
        color = self.COLOR_ONLINE if self._status else self.COLOR_OFFLINE

        painter.setBrush(Qt.transparent)
        painter.setPen(QPen(color, max(1, int(self.radius * 0.15))))

        # Three concentric arcs, smallest to largest
        # Each centred on (0, 0), radiating upward (30° → 150°)
        for i in range(1, 4):
            r = self.radius * i / 3
            rect = QRectF(-r, -r, 2 * r, 2 * r)
            painter.drawArc(rect, 30 * 16, 120 * 16)

        # Strike-through diagonal when offline
        if not self._status:
            painter.setPen(QPen(self.COLOR_OFFLINE, max(1, int(self.radius * 0.15))))
            painter.drawLine(
                QPointF(-self.radius * 0.6,  self.radius * 0.6),
                QPointF( self.radius * 0.6, -self.radius * 0.6),
            )

        # API address — always shown, colour indicates state
        if self._api:
            api_color = self.COLOR_API_ON if self._status else self.COLOR_API_OFF
            painter.setPen(QPen(api_color))
            font = QFont()
            font.setPointSizeF(max(6.0, self.radius * 0.4))
            painter.setFont(font)
            painter.drawText(
                QRectF(-self.radius * 2, self.radius * 0.7,
                        self.radius * 4,  self.radius * 0.8),
                Qt.AlignHCenter | Qt.AlignTop,
                self._api,
            )


class WarningDisplay(SceneItem):
    """
    Blinking red exclamation badge.
    Shown as a plain child of GraphComponent (not in group).

    Usage:
        self._warning.show_warning(True)   # start blinking
        self._warning.show_warning(False)  # hide and stop
    """

    COLOR        = QColor("RGB(255, 0, 0)")
    ALPHA_ON     = 255
    ALPHA_OFF    = 70
    BLINK_FPS    = 2          # 2 toggles/sec = 500 ms interval
    CORNER_RATIO = 1.8 / 14   # corner radius as fraction of size

    def __init__(self, size: int = 14, parent=None):
        super().__init__(width=size, height=size, parent=parent)
        self._on: bool = True

    # ── public API ────────────────────────────────────────────────

    def show_warning(self, visible: bool) -> None:
        """Start or stop the blinking warning badge."""
        self.setVisible(visible)
        if visible:
            self._on = True
            self.start_animation(fps=self.BLINK_FPS)
        else:
            self.stop_animation()

    # ── SceneItem hook ────────────────────────────────────────────

    def _on_timer(self) -> None:
        """Toggle blink state on each timer tick."""
        self._on = not self._on
        self.update()

    # ── painting ──────────────────────────────────────────────────

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(painter.Antialiasing, True)

        w, h = self.width, self.height
        r = min(w * self.CORNER_RATIO, w / 2, h / 2)

        # Centred rect to match SceneItem.boundingRect()
        rect = QRectF(-w / 2, -h / 2, w, h)

        # Red rounded background — blinks via alpha
        alpha = self.ALPHA_ON if self._on else self.ALPHA_OFF
        bg_path = QPainterPath()
        bg_path.addRoundedRect(rect, r, r)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(self.COLOR))
        painter.setOpacity(alpha / 255.0)
        painter.drawPath(bg_path)

        # White exclamation mark — normalised to item size
        painter.save()
        painter.setOpacity(alpha / 255.0)
        s = min(w, h)

        stem_w = 0.16 * s
        stem_h = 0.55 * s
        stem_top = -0.35 * s
        stem_rect = QRectF(-stem_w / 2, stem_top, stem_w, stem_h)
        stem_path = QPainterPath()
        stem_path.addRoundedRect(stem_rect, stem_w / 2, stem_w / 2)

        dot_d = 0.18 * s
        dot_rect = QRectF(-dot_d / 2, 0.24 * s, dot_d, dot_d)
        dot_path = QPainterPath()
        dot_path.addEllipse(dot_rect)

        painter.setBrush(QBrush(Qt.white))
        painter.setPen(Qt.NoPen)
        painter.drawPath(stem_path)
        painter.drawPath(dot_path)
        painter.restore()


class StatusOverlay(SceneItem):
    """
    Semi-transparent tinted rectangle drawn over the component figure.

    Hidden by default. Positioned and shown programmatically by GraphComponent
    to communicate run-time status (active, error, idle) without re-drawing
    the underlying figure.

    Usage:
        self._overlay.set_status(StatusOverlay.COLOR_ACTIVE)
        self._overlay.setVisible(True)
    """

    COLOR_ACTIVE: QColor = QColor(0, 200, 83, 120)    # semi-transparent green
    COLOR_ERROR:  QColor = QColor(229, 57, 53, 120)   # semi-transparent red
    COLOR_IDLE:   QColor = QColor(158, 158, 158, 80)  # semi-transparent grey

    def __init__(self, dimension: int = PATTERN_DIMENSION, parent=None):
        super().__init__(width=dimension, height=dimension, parent=parent)
        self._color: QColor = self.COLOR_IDLE

    # ── public API ────────────────────────────────────────────────

    def set_status(self, color: QColor) -> None:
        """Set the overlay tint colour and schedule a repaint."""
        self._color = color
        self.update()

    # ── painting ──────────────────────────────────────────────────

    def paint(self, painter, option, widget=None) -> None:
        painter.setRenderHint(painter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(self._color))
        w, h = self.width, self.height
        painter.drawRoundedRect(QRectF(-w / 2, -h / 2, w, h), 4, 4)