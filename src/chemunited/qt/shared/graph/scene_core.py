from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QGraphicsScene
from qfluentwidgets import isDarkTheme


class SceneCore(QGraphicsScene):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._dark_background_enabled = False
        self.sync_theme()

    @property
    def dark_background_enabled(self) -> bool:
        return self._dark_background_enabled

    def background_color(self) -> QColor:
        if self._dark_background_enabled:
            return QColor(30, 30, 30)
        if isDarkTheme():
            return QColor(39, 39, 39)
        return QColor(249, 249, 249)

    def set_dark_background_enabled(self, enabled: bool) -> None:
        self._dark_background_enabled = enabled
        self.setBackgroundBrush(self.background_color())
        self.update()
        for view in self.views():
            view.viewport().update()

    def toggle_dark_background(self) -> None:
        self.set_dark_background_enabled(not self._dark_background_enabled)

    def sync_theme(self):
        self.setBackgroundBrush(self.background_color())
        self.update()
        for view in self.views():
            view.viewport().update()
