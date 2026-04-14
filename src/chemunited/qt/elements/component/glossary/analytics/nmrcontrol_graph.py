from chemunited.core.components import ComponentData, ComponentMode
from chemunited.qt.elements.component.graph_item import GraphComponent
from .spectrum import Spectrum
from PyQt5.QtCore import Qt, QPointF
from typing import ClassVar


class NMRControl(GraphComponent[ComponentData]):
    METADATA: ClassVar[type[ComponentData]] = ComponentData
    BASEMODE: ClassVar[type[ComponentMode]] = ComponentMode

    def build(self, svg_path: str | None = None) -> None:
        self._data.ports_by_number[1].relative_position = (-28, -10)
        self._data.ports_by_number[2].relative_position = (28, -10)
        super().build(svg_path=f":/components_icons/components/NMRControl.svg")

        self.spectrum = Spectrum(
            width=50, height=20, color=Qt.yellow, parent=self
        )

        self.spectrum.setPos(
            QPointF(
                -25,
                -55,
            )
        )

        self.addToGroup(self.spectrum)
