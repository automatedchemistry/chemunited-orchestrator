from chemunited.core.components.glossary.rotary_valve import ValvePortLayout
from chemunited.core.common.enums import GroupParameterCategory
from chemunited.core.components import ValveMode, ValveComponentData
from chemunited.qt.elements.component.graph_item import GraphComponent
from pydantic import Field
from dataclasses import dataclass, field
from typing import ClassVar


@dataclass
class SolenideValveData(ValveComponentData):
    stator_ports: ValvePortLayout = field(
        default_factory=lambda: [(None, 1, None, 2), (None,)])
    rotor_ports: ValvePortLayout = field(
        default_factory=lambda: [(3, None, 3, None), (None,)])

    def internal_structure(self):
        super().internal_structure()
        self.ports_by_number[1].relative_position = (-45, 25)
        self.ports_by_number[2].relative_position = (45, 25)


class SolenideValveMode(ValveMode):
    normally_open: bool = Field(
        default=True,
        title="Normally open/close",
        description="The status of the valve when it is not energised - Open (allows fluid pass through)",
        json_schema_extra={
            "group": GroupParameterCategory.PROPERTY.value,
            "on_text": "Normally Open",
            "off_text": "Normally Close",
        },
    )
    opened: bool = Field(
        default=True,
        title="Status - open/close",
        description="The actual valve status",
        json_schema_extra={
            "group": GroupParameterCategory.PROPERTY.value,
            "on_text": "Open",
            "off_text": "Close",
        },
    )


class SolenoidValve(GraphComponent[SolenideValveData]):
    METADATA: ClassVar[type[SolenideValveData]] = SolenideValveData
    BASEMODE: ClassVar[type[SolenideValveMode]] = SolenideValveMode


@dataclass
class SolenideValve2WayData(ValveComponentData):
    stator_ports: ValvePortLayout = field(
        default_factory=lambda: [(1, 2), (0,)])
    rotor_ports: ValvePortLayout = field(
        default_factory=lambda: [(3, None), (3,)])

    def internal_structure(self):
        super().internal_structure()
        self.ports_by_number[0].relative_position = (40, 20)
        self.ports_by_number[1].relative_position = (-40, 8)
        self.ports_by_number[2].relative_position = (-40, 30)



class SolenoidValve2Way(GraphComponent[SolenideValve2WayData]):
    METADATA: ClassVar[type[SolenideValve2WayData]] = SolenideValve2WayData
    BASEMODE: ClassVar[type[SolenideValveMode]] = SolenideValveMode