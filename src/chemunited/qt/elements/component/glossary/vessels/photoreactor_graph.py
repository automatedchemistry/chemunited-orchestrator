from dataclasses import dataclass
from typing import ClassVar, override

from chemunited.core.common.enums import ConnectionType
from chemunited.core.components import PlugFlowComponentData, PlugFlowMode
from chemunited.core.components.internals import Port
from chemunited.qt.elements.component.graph_item import GraphComponent


@dataclass
class PhotoreactorData(PlugFlowComponentData):
    @override
    def internal_structure(self):
        super().internal_structure()
        self.port_pairs.append((3,))
        self.ports_by_number[3] = Port(
            number=3,
            component=self.name,
            category=ConnectionType.HEAT,
            relative_position=(0, -1),
        )


class Photoreactor(GraphComponent[PhotoreactorData]):
    METADATA: ClassVar[type[PhotoreactorData]] = PhotoreactorData
    BASEMODE: ClassVar[type[PlugFlowMode]] = PlugFlowMode
