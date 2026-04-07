from typing import ClassVar

from chemunited.core.components import ComponentMode, NeutralComponentData
from chemunited.qt.elements.component.graph_item import GraphComponent


class LengthControl(GraphComponent[NeutralComponentData]):
    METADATA: ClassVar[type[NeutralComponentData]] = NeutralComponentData
    BASEMODE: ClassVar[type[ComponentMode]] = ComponentMode
