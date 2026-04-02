from chemunited.qt.draw.elements.component import Components
from PyQt5.QtCore import QObject
from loguru import logger
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chemunited.qt.setup import MainWindow


class OrchestratorCore(QObject):
    def __init__(self, parent: MainWindow):
        super().__init__(parent)
        self.parent_ref = parent
        
        """Basic attributes"""

        # Components used in the platform (devices and utensils)
        self.components: Components = Components()
