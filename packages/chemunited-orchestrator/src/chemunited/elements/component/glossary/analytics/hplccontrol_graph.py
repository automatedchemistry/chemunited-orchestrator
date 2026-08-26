from typing import ClassVar

from chemunited_core.components import ComponentData
from PyQt5.QtCore import QPointF, Qt

from chemunited.elements.component.graph_item import GraphComponent

from .spectrum import Spectrum


class HPLCControl(GraphComponent[ComponentData]):
    FIGURE: ClassVar[str] = "HPLCControl"

    def build(self) -> None:
        super().build()

        self.spectrum = Spectrum(
            width=80, height=20, color=Qt.blue, parent=self  # type: ignore
        )

        self.spectrum.setPos(
            QPointF(
                -40,
                -110,
            )
        )

        self.addToGroup(self.spectrum)
