from typing import ClassVar

from chemunited.core.components import FlowSourceData, FlowSourceMode
from chemunited.qt.draw.elements.component.graph_item import GraphComponent


class SyringePump(GraphComponent[FlowSourceData]):
    METADATA: ClassVar[type[FlowSourceData]] = FlowSourceData
    BASEMODE: ClassVar[type[FlowSourceMode]] = FlowSourceMode
