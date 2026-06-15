from typing import ClassVar

from chemunited_core.components import ComponentData
from PyQt5.QtCore import QPointF, Qt

from chemunited.elements.component.graph_item import GraphComponent

from .spectrum import Spectrum


class MSControl(GraphComponent[ComponentData]):
    FIGURE: ClassVar[str] = "MSControl"

    def build(self) -> None:
        super().build()

        self.spectrum = Spectrum(width=50, height=20, color=Qt.green, parent=self)

        self.spectrum.setPos(
            QPointF(
                -25,
                -55,
            )
        )

        self.addToGroup(self.spectrum)
