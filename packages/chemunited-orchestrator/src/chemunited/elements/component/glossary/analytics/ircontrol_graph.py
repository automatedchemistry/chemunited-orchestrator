from typing import ClassVar

from chemunited_core.components import ComponentData
from PyQt5.QtCore import QPointF

from chemunited.elements.component.graph_item import GraphComponent

from .spectrum import Spectrum


class IRControl(GraphComponent[ComponentData]):
    FIGURE: ClassVar[str] = "IRControl"

    def build(self) -> None:
        super().build()

        self.spectrum = Spectrum(width=50, height=20, parent=self)

        self.spectrum.setPos(
            QPointF(
                -25,
                -55,
            )
        )

        self.addToGroup(self.spectrum)
