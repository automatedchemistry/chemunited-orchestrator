from typing import ClassVar

from chemunited.core.components import ComponentMode, NeutralComponentData
from chemunited.qt.draw.elements.component.graph_item import GraphComponent


class Pool(GraphComponent[NeutralComponentData]):
    METADATA: ClassVar[type[NeutralComponentData]] = NeutralComponentData
    BASEMODE: ClassVar[type[ComponentMode]] = ComponentMode
