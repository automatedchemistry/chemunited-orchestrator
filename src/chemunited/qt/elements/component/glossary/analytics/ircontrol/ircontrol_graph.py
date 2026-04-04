from typing import ClassVar

from chemunited.core.components import ComponentData, ComponentMode
from chemunited.qt.draw.elements.component.graph_item import GraphComponent


class IRControl(GraphComponent[ComponentData]):
    METADATA: ClassVar[type[ComponentData]] = ComponentData
    BASEMODE: ClassVar[type[ComponentMode]] = ComponentMode
