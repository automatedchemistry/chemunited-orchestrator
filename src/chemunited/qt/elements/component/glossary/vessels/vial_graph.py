from typing import ClassVar

from chemunited.core.components import VesselComponentData, VesselMode
from chemunited.qt.elements.component.graph_item import GraphComponent


class Vial(GraphComponent[VesselComponentData]):
    METADATA: ClassVar[type[VesselComponentData]] = VesselComponentData
    BASEMODE: ClassVar[type[VesselMode]] = VesselMode
