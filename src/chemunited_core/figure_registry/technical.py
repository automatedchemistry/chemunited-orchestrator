from dataclasses import dataclass, field

from pydantic import Field
from typing_extensions import override

from chemunited_core.common.enums import ConnectionType, GroupParameterCategory
from chemunited_core.components import ComponentMode, NeutralComponentData
from chemunited_core.components.command import PutResult
from chemunited_core.components.internals import Port


class MultiChannelMode(ComponentMode):
    channels: int = Field(
        default=8,
        title="Number of Channels",
        description="Number of Channels",
        json_schema_extra={
            "group": GroupParameterCategory.GENERAL.value,
            "editable": False,
            "creation_editable": True,
        },
        ge=1,
        le=32,
    )


@dataclass
class MultiChannelData(NeutralComponentData):
    channels: int = 8
    active: list[bool] = field(default_factory=list)

    @override
    def internal_structure(self) -> None:
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


@dataclass
class MultiChannelRelayData(MultiChannelData):
    @override
    def apply(self, command: str, **kwargs) -> PutResult:
        if command == "power-on":
            self._set_channel(kwargs.get("channel"), True)
        elif command == "power-off":
            self._set_channel(kwargs.get("channel"), False)
        elif command == "multiple_channel":
            values = str(kwargs.get("values", ""))
            for i in range(self.channels):
                digit = values[i] if i < len(values) else "0"
                self.active[i] = digit.isdigit() and int(digit) > 0
        return PutResult()

    def _set_channel(self, channel: str | int | None, state: bool) -> None:
        if channel is None:
            return
        index = int(channel) - 1
        if 0 <= index < len(self.active):
            self.active[index] = state


class StirringControlMode(ComponentMode):
    set_point: int = Field(
        default=0,
        title="Set Point",
        description="Set point for the stirring control (rpm)",
        json_schema_extra={
            "group": GroupParameterCategory.GENERAL.value,
            "editable": True,
        },
        ge=0,
        le=1000,
    )


@dataclass
class StirringControlData(NeutralComponentData): ...
