from typing import ClassVar

from PyQt5.QtCore import QRectF, Qt, Qt
from PyQt5.QtCore import QRectF
from chemunited_core.common.constant import PATTERN_DIMENSION
from chemunited_core.common.enums import ConnectionType
from chemunited_core.components import VesselComponentData
from chemunited_core.components.enums import PortAccess
from chemunited_core.figure_registry import get_figure_path

from chemunited.elements.component.component_parts import SvgLayer
from chemunited.elements.component.graph_item import GraphComponent
from .common import FlaskContent


class FlaskContent(FlaskContent):
    def __init__(self, width=40, height=40, parent=None) -> None:
        super().__init__(width=width, height=height, parent=parent)

    def paint(self, painter, option, widget=None) -> None:
        color = self.content_color()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        fill = 0 # Empty as default
        if getattr(self.parent_ref, 'inf', None) and getattr(self.parent_ref.inf, 'internal_inventories', None):
            inventory = next(iter(self.parent_ref.inf.internal_inventories.values()), None)
            if inventory and inventory.liq_content.volume > 0:
                fill = inventory.liq_content.volume / self.parent_ref.inf.capacity

        rect = QRectF(
            -self.width/2, 
            self.height/2 - self.height * fill, 
            self.width, 
            self.height * fill
        )
        painter.drawRoundedRect(rect, 5, 5)


class CustomFlask(GraphComponent[VesselComponentData]):
    FIGURE: ClassVar[str] = "CustomFlask"

    def build(self) -> None:
        # Content item
        self._content_item = FlaskContent(
            width=PATTERN_DIMENSION * self.SVG_SCALE * 0.6, 
            height=PATTERN_DIMENSION * self.SVG_SCALE, 
            parent=self
        )
        self.addToGroup(self._content_item)

        if self._data.heat_exchange:
            self._svg_jacket = SvgLayer.from_bytes(
                get_figure_path("FlaskJacket").read_bytes(),
                scale=PATTERN_DIMENSION * self.SVG_SCALE,
                parent=self,
            )
            self._svg_jacket.moveBy(0, 8)
            self.addToGroup(self._svg_jacket)

        for i, port in self._data.ports_by_number.items():
            if i == 1 and self._data.pressure_access:
                self._svg_pressure_access = SvgLayer.from_bytes(
                    get_figure_path("BottlePressureAccess").read_bytes(),
                    scale=10 * self.SVG_SCALE,
                    parent=self,
                )
                self._svg_pressure_access.moveBy(25, -58)
                port.relative_position = (25, -68)
                self.addToGroup(self._svg_pressure_access)
            elif (
                port.category == ConnectionType.HYDRAULIC
                and port.access == PortAccess.TOP
            ):
                _svg_access = SvgLayer.from_bytes(
                    get_figure_path("BottleAccess").read_bytes(),
                    scale=40 * self.SVG_SCALE,
                    parent=self,
                )
                _svg_access.moveBy(
                    port.relative_position[0], port.relative_position[1] + 40
                )
                self.addToGroup(_svg_access)

        super().build()
