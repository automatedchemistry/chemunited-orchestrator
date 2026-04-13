from chemunited.core.components import FlowSourceData, FlowSourceMode
from chemunited.qt.elements.component.graph_item import GraphComponent
from chemunited.qt.elements.component.component_parts.svg_layer import SvgLayer
from chemunited.core.common.constant import PATTERN_DIMENSION
from PyQt5.QtCore import QFile
from typing import ClassVar



class SyringePump(GraphComponent[FlowSourceData]):
    METADATA: ClassVar[type[FlowSourceData]] = FlowSourceData
    BASEMODE: ClassVar[type[FlowSourceMode]] = FlowSourceMode

    def build(self) -> None:
        svg_path = f":/components_icons/components/SyringePlunger.svg"
        if QFile.exists(svg_path):
            self._syringe_plunger = SvgLayer(
                svg_path,
                angle=self._data.angle,
                scale=PATTERN_DIMENSION * 1.2,
                parent=self,
            )
            self._syringe_plunger.moveBy(2.5, 11.5)
            self.addToGroup(self._syringe_plunger)
        super().build(svg_path=f":/components_icons/components/SyringeBarrel.svg")
        