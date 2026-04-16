from typing import ClassVar

from PyQt5.QtCore import QPointF, Qt

from chemunited.core.components import ComponentData, ComponentMode
from chemunited.qt.elements.component.graph_item import GraphComponent

from .spectrum import Spectrum


class MSControl(GraphComponent[ComponentData]):
    METADATA: ClassVar[type[ComponentData]] = ComponentData
    BASEMODE: ClassVar[type[ComponentMode]] = ComponentMode

    def build(self, svg_path: str | None = None) -> None:
        self._data.ports_by_number[1].relative_position = (-40, -40)
        self._data.ports_by_number[2].relative_position = (-25, -40)
        super().build(svg_path=":/components_icons/components/MSControl.svg")

        self.spectrum = Spectrum(width=50, height=20, color=Qt.green, parent=self)

        self.spectrum.setPos(
            QPointF(
                -25,
                -55,
            )
        )

        self.addToGroup(self.spectrum)
