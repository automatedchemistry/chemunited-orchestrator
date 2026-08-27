import math
import sys

from PyQt5.QtCore import QElapsedTimer, QRect, Qt, QTimer
from PyQt5.QtGui import QColor, QPainter, QPen
from PyQt5.QtSvg import QSvgWidget
from PyQt5.QtWidgets import QApplication, QVBoxLayout, QWidget


class SmoothWaitingArc(QWidget):
    """Rotating arc that grows and shrinks smoothly (indeterminate spinner)."""

    def __init__(self, parent=None):
        super().__init__(parent)

        # Animation state
        self.base_angle = 0
        self.phase = 0.0  # drives growth/shrink

        # Timer
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_animation)
        self.timer.start(16)  # ~60 FPS

    def update_animation(self):
        # Rotate continuously
        self.base_angle = (self.base_angle + 4 * 16) % (360 * 16)

        # Update growth phase
        self.phase += 0.05
        self.update()

    def paintEvent(self, a0):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = QRect(50, 40, 200, 200)

        # Arc pen
        pen = QPen(QColor(100, 180, 80), 8, Qt.SolidLine, Qt.RoundCap)  # type: ignore[attr-defined]
        painter.setPen(pen)

        # Span angle oscillates between small and large (sinusoidal)
        min_span = 20 * 16  # ~20°
        max_span = 150 * 16  # ~150°
        span = min_span + (max_span - min_span) * (0.5 * (1 + math.sin(self.phase)))

        # Draw the arc
        painter.drawArc(rect, self.base_angle, int(span))


class WaitingWindow(QWidget):
    """Splash screen with logo + animated waiting circle in front."""

    def __init__(self):
        super().__init__()

        # Frameless + transparent background
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.SplashScreen)  # type: ignore[attr-defined]
        self.setAttribute(Qt.WA_TranslucentBackground)  # type: ignore[attr-defined]

        # Layout with logo
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Logo
        self.logo = QSvgWidget(":/icons/icons/chemunited.svg", self)
        self.logo.setFixedSize(175, 175)
        layout.addWidget(self.logo, alignment=Qt.AlignCenter)  # type: ignore[attr-defined]

        # Waiting circle overlay
        self.waiting_circle = SmoothWaitingArc(self)
        self.waiting_circle.resize(self.size())
        self.waiting_circle.raise_()

        self.resize(300, 300)

        # Auto-close after 5s
        # QTimer.singleShot(5000, self.close)

    def resizeEvent(self, a0):
        self.waiting_circle.resize(self.size())
        super().resizeEvent(a0)


def show_waiting(n: int):
    # Run event loop manually for ~n seconds
    # --- Show splash ---
    splash = WaitingWindow()
    splash.show()
    # Run event loop manually for ~2 seconds
    timer = QElapsedTimer()
    timer.start()
    while timer.elapsed() < n * 1000:
        QApplication.processEvents()
    return splash


if __name__ == "__main__":
    from chemunited import resources_rc  # noqa: F401

    app = QApplication(sys.argv)

    show_waiting(3)

    sys.exit(app.exec_())
