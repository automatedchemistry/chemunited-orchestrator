from typing import ClassVar

from chemunited_core.common.constant import PATTERN_DIMENSION
from chemunited_core.common.enums import ConnectionType
from chemunited_core.components.enums import PortAccess
from chemunited_core.figure_registry import get_figure_path
from chemunited_core.figure_registry.vessels import GlassBottleData
from PyQt5.QtCore import QRectF, Qt

from chemunited.elements.component.component_parts import SvgLayer
from chemunited.elements.component.graph_item import GraphComponent

from .common import FlaskContent


class GlassBottleContent(FlaskContent):
    def paint(self, painter, option, widget=None) -> None:
        color = self.content_color()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)

        fill = 0.0
        component_data = getattr(self.parent_ref, "inf", None)
        inventories = getattr(component_data, "internal_inventories", {})
        inventory = next(iter(inventories.values()), None)
        capacity = float(getattr(component_data, "capacity_value", 0.0) or 0.0)
        if inventory is not None and capacity > 0:
            fill = inventory.liq_content.volume / capacity
            fill = max(0.0, min(1.0, fill))

        rect = QRectF(
            -self.width / 2,
            self.height / 2 - self.height * fill,
            self.width,
            self.height * fill,
        )
        painter.drawRoundedRect(rect, 15, 15)


class GlassBottle(GraphComponent[GlassBottleData]):
    FIGURE: ClassVar[str] = "GlassBottle"

    def __init__(self, data: GlassBottleData) -> None:
        self._content_item: GlassBottleContent | None = None
        super().__init__(data)

    def build(self) -> None:
        self._content_item = GlassBottleContent(
            width=int(PATTERN_DIMENSION * self.SVG_SCALE * 0.55),
            height=int(PATTERN_DIMENSION * self.SVG_SCALE),
            parent=self,
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
