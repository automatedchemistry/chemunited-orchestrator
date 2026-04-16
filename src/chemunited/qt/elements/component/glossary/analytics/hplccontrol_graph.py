from typing import ClassVar

from PyQt5.QtCore import QPointF, Qt

from chemunited.core.components import ComponentData, ComponentMode
from chemunited.qt.elements.component.graph_item import GraphComponent

from .spectrum import Spectrum


class HPLCControl(GraphComponent[ComponentData]):
    METADATA: ClassVar[type[ComponentData]] = ComponentData
    BASEMODE: ClassVar[type[ComponentMode]] = ComponentMode

    def build(self, svg_path: str | None = None) -> None:
        super().build(svg_path=":/components_icons/components/HPLC.svg")

        self.spectrum = Spectrum(width=50, height=20, color=Qt.blue, parent=self)

        self.spectrum.setPos(
            QPointF(
                -25,
                -55,
            )
        )

        self.addToGroup(self.spectrum)
