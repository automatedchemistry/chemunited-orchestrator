from typing import ClassVar

from chemunited_core.common.constant import PATTERN_DIMENSION
from chemunited_core.common.enums import ConnectionType
from chemunited_core.components import VesselComponentData
from chemunited_core.components.enums import PortAccess
from chemunited_core.figure_registry import get_figure_path

from chemunited.qt.elements.component.component_parts import SvgLayer
from chemunited.qt.elements.component.graph_item import GraphComponent


class CustomFlask(GraphComponent[VesselComponentData]):
    FIGURE: ClassVar[str] = "CustomFlask"

    def build(self) -> None:
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
