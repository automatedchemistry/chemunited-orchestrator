from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QGraphicsScene
from qfluentwidgets import isDarkTheme


class SceneCore(QGraphicsScene):
    def __init__(self, parent=None):
        super().__init__(parent)

    def sync_theme(self):
        if isDarkTheme():
            self.setBackgroundBrush(QColor(0, 0, 0, 0))
        else:
            self.setBackgroundBrush(QColor(255, 255, 255, 0))
        self.update()
