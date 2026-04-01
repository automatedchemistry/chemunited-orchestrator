from typing import ClassVar
from chemunited.core.components import NeutralComponentData, ComponentMode
from chemunited.qt.shared.elements.component.graph_item import GraphComponent


class PowerControl(GraphComponent[NeutralComponentData]):
    METADATA: ClassVar[type[NeutralComponentData]] = NeutralComponentData
    BASEMODE: ClassVar[type[ComponentMode]] = ComponentMode


class PowerSwitch(GraphComponent[NeutralComponentData]):
    METADATA: ClassVar[type[NeutralComponentData]] = NeutralComponentData
    BASEMODE: ClassVar[type[ComponentMode]] = ComponentMode


class PhidgetBubbleSensorPowerComponent(GraphComponent[NeutralComponentData]):
    METADATA: ClassVar[type[NeutralComponentData]] = NeutralComponentData
    BASEMODE: ClassVar[type[ComponentMode]] = ComponentMode
