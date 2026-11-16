from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QGraphicsTextItem
from qfluentwidgets import isDarkTheme


class TextElement(QGraphicsTextItem):
    """
    Theme-aware text item for use inside the platform scene.
    Reads isDarkTheme() at paint time so theme switches
    are reflected without recreation.
    """

    def __init__(self, text: str = "", font: QFont | None = None, parent=None):
        super().__init__(text, parent=parent)
        if font is not None:
            self.setFont(font)

    def paint(self, painter, option, widget=None):
        color = Qt.white if isDarkTheme() else Qt.black
        self.setDefaultTextColor(color)
        super().paint(painter, option, widget)
