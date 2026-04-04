from typing import ClassVar

from chemunited.core.components import gantry3DData, gantry3DMode
from chemunited.qt.elements.component.graph_item import GraphComponent


class Gantry3D(GraphComponent[gantry3DData]):
    METADATA: ClassVar[type[gantry3DData]] = gantry3DData
    BASEMODE: ClassVar[type[gantry3DMode]] = gantry3DMode
