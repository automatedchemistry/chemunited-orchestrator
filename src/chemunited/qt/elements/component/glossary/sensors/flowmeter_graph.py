from chemunited.core.components import ComponentData, ComponentMode
from chemunited.qt.elements.component.graph_item import GraphComponent
from typing import ClassVar


class FlowMeter(GraphComponent[ComponentData]):
    METADATA: ClassVar[type[ComponentData]] = ComponentData
    BASEMODE: ClassVar[type[ComponentMode]] = ComponentMode

    
