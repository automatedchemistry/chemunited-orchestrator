from typing import ClassVar

from chemunited_core.figure_registry import Gantry3DData, Gantry3DMode
from chemunited.qt.elements.component.graph_item import GraphComponent


class Gantry3D(GraphComponent[Gantry3DData]):
    METADATA: ClassVar[type[Gantry3DData]] = Gantry3DData
    BASEMODE: ClassVar[type[Gantry3DMode]] = Gantry3DMode
    SVG_SCALE: ClassVar[float] = 4.0
