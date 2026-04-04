from typing import ClassVar

from chemunited.core.components import VesselComponentData, VesselMode
from chemunited.qt.draw.elements.component.graph_item import GraphComponent


class PressureGlassBottle(GraphComponent[VesselComponentData]):
    METADATA: ClassVar[type[VesselComponentData]] = VesselComponentData
    BASEMODE: ClassVar[type[VesselMode]] = VesselMode
