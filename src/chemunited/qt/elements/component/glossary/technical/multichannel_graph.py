from chemunited.core.components import NeutralComponentData, ComponentMode
from chemunited.qt.elements.component.graph_item import GraphComponent
from chemunited.qt.elements.component.component_parts import SceneItem
from chemunited.core.common.enums import GroupParameterCategory
from chemunited.core.common.enums import ConnectionType
from chemunited.core.components.internals import Port
from PyQt5.QtGui import QPen, QBrush, QColor
from PyQt5.QtCore import Qt
from pydantic import Field
from typing import ClassVar


class MultiChannelBory(SceneItem):

    def __init__(self, data: MultiChannelData) -> None:
        self._data = data
        super().__init__(
            width=15,
            height=16 * data.channels + 4
        )

    def paint(self, painter, option, widget = None) -> None:
        painter.setPen(QPen(Qt.black, 1))
        painter.setBrush(QBrush(Qt.white))
        painter.drawRect(self.boundingRect())
        value = self._data.active
        r = 4
        for i in range(self._data.channels):
            if value:
                color = QColor("#8BC34A") if value[i] else QColor("#E8F5E9")
                painter.setPen(QPen(color, 2))
            painter.drawEllipse(
                -r, 
                int(-self.height / 2 + i * 16 + 4), 
                2 * r, 
                2 * r
            )


class MultiChannelMode(ComponentMode):
    channels: int = Field(
        default=8,
        title="Number of Channels",
        description="Number of Channels",
        json_schema_extra={
            "group": GroupParameterCategory.GENERAL.value,
            "editable": True,
        },
        ge=1, 
        le=32
    )


class MultiChannelData(NeutralComponentData):
    channels: int = 8
    active: list[bool] = []

    def internal_structure(self):
        self.active = [False] * self.channels
        self.port_pairs = [(i + 1,) for i in range(self.channels)]
        self.ports_by_number = {
            i: Port(
                number=i,
                component=self.name,
                relative_position=(0, - (self.channels * 8 + 10) + i * 16),
                category=ConnectionType.ELECTRONIC
            )
            for i in range(1, self.channels + 1)
        }
        self.internal_edges = {}
        self.internal_inventory = None


class MultiChannelADC(GraphComponent[MultiChannelData]):
    METADATA: ClassVar[type[MultiChannelData]] = MultiChannelData
    BASEMODE: ClassVar[type[MultiChannelMode]] = MultiChannelMode
    SVG_SCALE: ClassVar[float] = 0.8

    def build(self, svg_path: str | None = None) -> None:
        self.bory = MultiChannelBory(self._data)
        self.addToGroup(self.bory)
        super().build(svg_path=f":/components_icons/components/ADC.svg")
        self._svg.setPos(-20, self.bory.height /2)


class MultiChannelDAC(GraphComponent[MultiChannelData]):
    METADATA: ClassVar[type[MultiChannelData]] = MultiChannelData
    BASEMODE: ClassVar[type[MultiChannelMode]] = MultiChannelMode
    SVG_SCALE: ClassVar[float] = 0.8

    def build(self, svg_path: str | None = None) -> None:
        self.bory = MultiChannelBory(self._data)
        self.addToGroup(self.bory)
        super().build(svg_path=f":/components_icons/components/DAC.svg")
        self._svg.setPos(-20, self.bory.height /2)


class MultiChannelRelay(GraphComponent[MultiChannelData]):
    METADATA: ClassVar[type[MultiChannelData]] = MultiChannelData
    BASEMODE: ClassVar[type[MultiChannelMode]] = MultiChannelMode
    SVG_SCALE: ClassVar[float] = 0.8

    def build(self, svg_path: str | None = None) -> None:
        self.bory = MultiChannelBory(self._data)
        self.addToGroup(self.bory)
        super().build(svg_path=f":/components_icons/components/Relay.svg")
        self._svg.setPos(-20, self.bory.height /2)
