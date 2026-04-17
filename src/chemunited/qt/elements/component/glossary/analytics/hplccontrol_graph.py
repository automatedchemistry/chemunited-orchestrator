from typing import ClassVar

from PyQt5.QtCore import QPointF, Qt

from chemunited.core.components import ComponentData, ComponentMode
from chemunited.qt.elements.component.graph_item import GraphComponent

from .spectrum import Spectrum


class HPLCControl(GraphComponent[ComponentData]):
    METADATA: ClassVar[type[ComponentData]] = ComponentData
    BASEMODE: ClassVar[type[ComponentMode]] = ComponentMode
    SVG_SCALE: ClassVar[float] = 4.0

    def build(self, svg_path: str | None = None) -> None:
        self._data.ports_by_number[1].relative_position = (-55, 80)
        self._data.ports_by_number[2].relative_position = (55, 80)
        super().build(svg_path=":/components_icons/components/HPLC.svg")

        self.spectrum = Spectrum(
            width=80, 
            height=20, 
            color=Qt.blue,  # type: ignore
            parent=self
        )

        self.spectrum.setPos(
            QPointF(
                -40,
                -110,
            )
        )

        self.addToGroup(self.spectrum)
