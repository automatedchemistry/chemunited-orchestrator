from dataclasses import dataclass
from typing import ClassVar, override

from chemunited.core.common.enums import ConnectionType
from chemunited.core.components import NeutralComponentData, ComponentMode
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
                relative_position=(0, 1),
            )
        }


class PeltierCoolerTemperatureControl(
    GraphComponent[PeltierCoolerTemperatureControlData]
):
    METADATA: ClassVar[type[PeltierCoolerTemperatureControlData]] = (
        PeltierCoolerTemperatureControlData
    )
    BASEMODE: ClassVar[type[ComponentMode]] = ComponentMode
