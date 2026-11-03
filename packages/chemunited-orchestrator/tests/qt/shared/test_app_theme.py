from PyQt5.QtGui import QColor, QPalette
from PyQt5.QtWidgets import QApplication
from pytestqt.qtbot import QtBot
from qfluentwidgets import Theme, setTheme

from chemunited.shared.widgets.app_theme import apply_app_palette


def test_app_palette_follows_theme(qtbot: QtBot):
    original = QPalette(QApplication.palette())
    try:
        setTheme(Theme.DARK)
        apply_app_palette()
        dark = QApplication.palette()
        assert dark.color(QPalette.Window) == QColor(32, 32, 32)
        assert dark.color(QPalette.Base) == QColor(39, 39, 39)

        setTheme(Theme.LIGHT)
        apply_app_palette()
        assert QApplication.palette() == original
    finally:
        setTheme(Theme.LIGHT)
        QApplication.setPalette(original)
