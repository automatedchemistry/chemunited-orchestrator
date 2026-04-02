from typing import TYPE_CHECKING

from PyQt5.QtCore import QObject

from chemunited.qt.draw.elements.access import Components

if TYPE_CHECKING:
    from chemunited.qt.setup import SetupWindow


class OrchestratorCore(QObject):
    def __init__(self, parent: "SetupWindow"):
        super().__init__(parent)
        self.parent_ref = parent

        """Basic attributes"""

        # Components used in the platform (devices and utensils)
        self.components: Components = Components()
