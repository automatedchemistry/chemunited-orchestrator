from typing import ClassVar

from chemunited.core.components import PlugFlowComponentData, PlugFlowMode
from chemunited.qt.elements.component.graph_item import GraphComponent


class FlowReactor(GraphComponent[PlugFlowComponentData]):
    METADATA: ClassVar[type[PlugFlowComponentData]] = PlugFlowComponentData
    BASEMODE: ClassVar[type[PlugFlowMode]] = PlugFlowMode
