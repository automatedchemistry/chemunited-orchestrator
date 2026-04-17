from typing import ClassVar

from chemunited.core.components import ComponentMode, NeutralComponentData
from chemunited.qt.elements.component.graph_item import GraphComponent
from chemunited.core.components.internals import Port
from chemunited.core.common.enums import ConnectionType


class TemperatureControlData(NeutralComponentData):
    
    def internal_structure(self):
        self.port_pairs = [(1, 2)]
        self.ports_by_number = {
            1: Port(
                number=1,
                component=self.name,
                category=ConnectionType.HEAT,
                relative_position=(25, 0),
            ),
        }


class TemperatureControl(GraphComponent[TemperatureControlData]):
    METADATA: ClassVar[type[TemperatureControlData]] = TemperatureControlData
    BASEMODE: ClassVar[type[ComponentMode]] = ComponentMode

    def build(self, svg_path: str | None = None) -> None:
        return super().build(svg_path=f":/components_icons/components/Chiller.svg")
