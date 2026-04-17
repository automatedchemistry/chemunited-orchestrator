from dataclasses import dataclass
from typing import ClassVar, override

from chemunited.core.common.enums import ConnectionType
from chemunited.core.components import ComponentMode, NeutralComponentData
from chemunited.core.components.internals import Port
from chemunited.qt.elements.component.graph_item import GraphComponent


@dataclass
class PeltierCoolerTemperatureControlData(NeutralComponentData):
    @override
    def internal_structure(self):
        self.port_pairs = [(1,)]
        self.ports_by_number = {
            1: Port(
                number=1,
                component=self.name,
                category=ConnectionType.HEAT,
                relative_position=(50, 0),
            )
        }


class PeltierCoolerTemperatureControl(
    GraphComponent[PeltierCoolerTemperatureControlData]
):
    METADATA: ClassVar[type[PeltierCoolerTemperatureControlData]] = (
        PeltierCoolerTemperatureControlData
    )
    BASEMODE: ClassVar[type[ComponentMode]] = ComponentMode
    SVG_SCALE: ClassVar[float] = 2

    def build(self, svg_path: str | None = None) -> None:
        super().build(svg_path=":/components_icons/components/Peltier.svg")
