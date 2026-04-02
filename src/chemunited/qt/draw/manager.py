from .elements.component import Components
from PyQt5.QtCore import QObject
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chemunited.qt.setup import MainWindow


class DrawManager(QObject):
    """Manager for the draw frame"""
    def __init__(self, parent: MainWindow):
        super().__init__(parent)
        self.parent_ref = parent
        
        """Basic attributes"""

        # Components used in the platform (devices and utensils)
        self.components: Components = Components()

    def add_component(self):
        ...
