from typing import ClassVar

from chemunited_core.common.constant import PATTERN_DIMENSION
from chemunited_core.common.enums import ConnectionType
from chemunited_core.components import VesselComponentData, VesselMode
from chemunited_core.components.enums import PortAccess
from chemunited.qt.elements.component.component_parts import SvgLayer
from chemunited.qt.elements.component.graph_item import GraphComponent


class CustomFlask(GraphComponent[VesselComponentData]):
    METADATA: ClassVar[type[VesselComponentData]] = VesselComponentData
    BASEMODE: ClassVar[type[VesselMode]] = VesselMode

    def build(self, svg_path: str | None = None) -> None:
        if self._data.heat_exchange:
            jacket_svg_path = ":/components_icons/components/FlaskJacket.svg"
            self._svg_jacket = SvgLayer(
                jacket_svg_path,
                scale=PATTERN_DIMENSION * self.SVG_SCALE,
                parent=self,
            )
            self._svg_jacket.moveBy(0, 8)
            self.addToGroup(self._svg_jacket)

        for i, port in self._data.ports_by_number.items():
            if i == 1 and self._data.pressure_access:
                pressure_access_svg_path = (
                    ":/components_icons/components/BottlePressureAccess.svg"
                )
                self._svg_pressure_access = SvgLayer(
                    pressure_access_svg_path,
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
                access_svg_path = ":/components_icons/components/BottleAccess.svg"
                _svg_access = SvgLayer(
                    access_svg_path,
                    scale=40 * self.SVG_SCALE,
                    parent=self,
                )
                _svg_access.moveBy(
                    port.relative_position[0], port.relative_position[1] + 40
                )
                self.addToGroup(_svg_access)

        super().build(svg_path=":/components_icons/components/CustomFlask.svg")
