from typing import ClassVar
from chemunited.core.components import NeutralComponentData, ComponentMode
from chemunited.qt.shared.elements.component.graph_item import GraphComponent


class PeltierCoolerTemperatureControl(GraphComponent[NeutralComponentData]):
    METADATA: ClassVar[type[NeutralComponentData]] = NeutralComponentData
    BASEMODE: ClassVar[type[ComponentMode]] = ComponentMode
