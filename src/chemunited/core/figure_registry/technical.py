from dataclasses import dataclass, field
from typing import override

from pydantic import Field

from chemunited.core.common.enums import ConnectionType, GroupParameterCategory
from chemunited.core.components import ComponentMode, NeutralComponentData
from chemunited.core.components.internals import Port


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
        le=32,
    )


@dataclass
class MultiChannelData(NeutralComponentData):
    channels: int = 8
    active: list[bool] = field(default_factory=list)

    @override
    def internal_structure(self):
        self.active = [False] * self.channels
        self.port_pairs = [(i + 1,) for i in range(self.channels)]
        self.ports_by_number = {
            i: Port(
                number=i,
                component=self.name,
                relative_position=(0, -(self.channels * 8 + 10) + i * 16),
                category=ConnectionType.ELECTRONIC,
            )
            for i in range(1, self.channels + 1)
        }
        self.internal_edges = {}
        self.internal_inventories = {}
