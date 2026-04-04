from typing import ClassVar

from chemunited.core.components import JunctionData, JunctionMode
from chemunited.qt.draw.elements.component.graph_item import GraphComponent


class Distributor(GraphComponent[JunctionData]):
    METADATA: ClassVar[type[JunctionData]] = JunctionData
    BASEMODE: ClassVar[type[JunctionMode]] = JunctionMode
