from dataclasses import dataclass, field
from typing import ClassVar

from pydantic import Field
from typing_extensions import override

from chemunited_core.common.enums import ConnectionType, GroupParameterCategory
from chemunited_core.components import ComponentMode, PutResult, ValveComponentData
from chemunited_core.components.internals import Port
from chemunited_core.components.valve import ValvePortLayout

SOLENOID_VALVE_STATOR: ValvePortLayout = [(None, 1, None, 2), (None,)]
SOLENOID_VALVE_ROTOR: ValvePortLayout = [(None, 3, None, 3), (None,)]

SOLENOID_VALVE_2_WAY_STATOR: ValvePortLayout = [(1, 2), (0,)]
SOLENOID_VALVE_2_WAY_ROTOR: ValvePortLayout = [(3, None), (3,)]


def _copy_port_layout(layout: ValvePortLayout) -> ValvePortLayout:
    return [tuple(row) for row in layout]


def _layout_factory(layout: ValvePortLayout):
    def factory() -> ValvePortLayout:
        return _copy_port_layout(layout)

    return factory


class SolenoidValveMode(ComponentMode):
    normally_open: bool = Field(
        default=True,
        title="Normally open/close",
        description="The status of the valve when it is not energised.",
        json_schema_extra={
            "group": GroupParameterCategory.PROPERTY.value,
            "on_text": "Normally Open",
            "off_text": "Normally Close",
        },
    )
    opened: bool = Field(
        default=True,
        title="Status - open/close",
        description="The actual valve status.",
        json_schema_extra={
            "group": GroupParameterCategory.PROPERTY.value,
            "on_text": "Open",
            "off_text": "Close",
        },
    )


@dataclass
class SolenoidValveData(ValveComponentData):
    stator_ports: ValvePortLayout = field(
        default_factory=_layout_factory(SOLENOID_VALVE_STATOR)
    )
    rotor_ports: ValvePortLayout = field(
        default_factory=_layout_factory(SOLENOID_VALVE_ROTOR)
    )
    normally_open: bool = True
    opened: bool = True

    def put(self, command: str, **kwargs) -> PutResult:
        if command in ["open", "close"]:
            return PutResult()
        raise ValueError(f"Unknown command '{command}' for {type(self).__name__}.")

    def apply(self, command: str, **kwargs) -> PutResult:
        if command == "open":
            self.opened = True
            self.sync_internal_state()
        elif command == "close":
            self.opened = False
            self.sync_internal_state()
        elif command == "power-on":
            self.opened = not self.normally_open
            self.sync_internal_state()
        elif command == "power-off":
            self.opened = self.normally_open
            self.sync_internal_state()
        return PutResult()

    @override
    def internal_structure(self) -> None:
        super().internal_structure()
        self.ports_by_number[1].relative_position = (-22.5, 12.5)
        self.ports_by_number[2].relative_position = (22.5, 12.5)
        self.ports_by_number[3] = Port(
            number=3,
            component=self.name,
            category=ConnectionType.ELECTRONIC,
            relative_position=(-13, -8),
        )
        self.sync_internal_state()

    @override
    def sync_internal_state(self) -> None:
        super().sync_internal_state()
        if not self.opened:
            for edge in self.internal_edges.values():
                edge.close()


class SolenoidValve2WayMode(ComponentMode):
    normally_open: bool = Field(
        default=True,
        title="Position 1/2",
        description="The position selected when the valve is not energised.",
        json_schema_extra={
            "group": GroupParameterCategory.PROPERTY.value,
            "on_text": "Position 1",
            "off_text": "Position 2",
        },
    )
    opened: bool = Field(
        default=True,
        title="Position 1/2",
        description="The actual valve position.",
        json_schema_extra={
            "group": GroupParameterCategory.PROPERTY.value,
            "on_text": "Position 1",
            "off_text": "Position 2",
        },
    )


@dataclass
class SolenoidValve2WayData(ValveComponentData):
    stator_ports: ValvePortLayout = field(
        default_factory=_layout_factory(SOLENOID_VALVE_2_WAY_STATOR)
    )
    rotor_ports: ValvePortLayout = field(
        default_factory=_layout_factory(SOLENOID_VALVE_2_WAY_ROTOR)
    )
    normally_open: bool = True
    opened: bool = True
    hub_ports: ClassVar[tuple[int, ...]] = (0,)

    def put(self, command: str, **kwargs) -> PutResult:
        if command in ["open", "close"]:
            return PutResult()
        raise ValueError(f"Unknown command '{command}' for {type(self).__name__}.")

    def apply(self, command: str, **kwargs) -> PutResult:
        if command == "open":
            self.opened = True
            self.sync_internal_state()
        elif command == "close":
            self.opened = False
            self.sync_internal_state()
        elif command == "power-on":
            self.opened = not self.normally_open
            self.sync_internal_state()
        elif command == "power-off":
            self.opened = self.normally_open
            self.sync_internal_state()
        return PutResult()

    @override
    def internal_structure(self) -> None:
        super().internal_structure()
        self.ports_by_number[0].relative_position = (20, 10)
        self.ports_by_number[1].relative_position = (-20, 4)
        self.ports_by_number[2].relative_position = (-20, 15)
        self.ports_by_number[3] = Port(
            number=3,
            component=self.name,
            category=ConnectionType.ELECTRONIC,
            relative_position=(-13, -16),
        )
        self.sync_internal_state()

    @override
    def sync_internal_state(self) -> None:
        if self.opened:
            self.internal_edges[(0, 1)].open()
            self.internal_edges[(0, 2)].close()
        else:
            self.internal_edges[(0, 1)].close()
            self.internal_edges[(0, 2)].open()
