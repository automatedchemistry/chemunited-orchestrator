from dataclasses import dataclass, field

from pydantic import Field

from chemunited.core.common.enums import GroupParameterCategory
from chemunited.core.components.glossary.rotary_valve import (
    ValveComponentData,
    ValveMode,
    ValvePortLayout,
)

THREE_PORT_TWO_POSITION_STATOR: ValvePortLayout = [(None, 1, 2, 3), (0,)]
THREE_PORT_TWO_POSITION_ROTOR: ValvePortLayout = [(4, 4, None, None), (None,)]

THREE_PORT_FOUR_POSITION_STATOR: ValvePortLayout = [(None, 1, 2, 3), (0,)]
THREE_PORT_FOUR_POSITION_ROTOR: ValvePortLayout = [(4, 4, 5, 5), (4,)]

FOUR_PORT_FIVE_POSITION_STATOR: ValvePortLayout = [
    (None, None, 1, None, 2, None, 3, None),
    (0,),
]
FOUR_PORT_FIVE_POSITION_ROTOR: ValvePortLayout = [
    (None, 5, None, None, 4, None, 4, None),
    (5,),
]

SIX_PORT_TWO_POSITION_STATOR: ValvePortLayout = [(1, 2, 3, 4, 5, 6), (0,)]
SIX_PORT_TWO_POSITION_ROTOR: ValvePortLayout = [(7, 7, 8, 8, 9, 9), (None,)]

TWO_PORT_DISTRIBUTION_STATOR: ValvePortLayout = [(1, 2), (0,)]
TWO_PORT_DISTRIBUTION_ROTOR: ValvePortLayout = [(3, None), (3,)]

FOUR_PORT_DISTRIBUTION_STATOR: ValvePortLayout = [(1, 2, 3, 4), (0,)]
FOUR_PORT_DISTRIBUTION_ROTOR: ValvePortLayout = [(5, None, None, None), (5,)]

SIX_PORT_DISTRIBUTION_STATOR: ValvePortLayout = [(1, 2, 3, 4, 5, 6), (0,)]
SIX_PORT_DISTRIBUTION_ROTOR: ValvePortLayout = [
    (7, None, None, None, None, None),
    (7,),
]

TWELVE_PORT_DISTRIBUTION_STATOR: ValvePortLayout = [
    (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12),
    (0,),
]
TWELVE_PORT_DISTRIBUTION_ROTOR: ValvePortLayout = [
    (13, None, None, None, None, None, None, None, None, None, None, None),
    (13,),
]

SIXTEEN_PORT_DISTRIBUTION_STATOR: ValvePortLayout = [
    (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16),
    (0,),
]
SIXTEEN_PORT_DISTRIBUTION_ROTOR: ValvePortLayout = [
    (
        17,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    ),
    (17,),
]


def _copy_port_layout(layout: ValvePortLayout) -> ValvePortLayout:
    return [tuple(row) for row in layout]


def _layout_factory(layout: ValvePortLayout):
    def factory() -> ValvePortLayout:
        return _copy_port_layout(layout)

    return factory


def _mode_field(layout: ValvePortLayout, *, title: str, description: str):
    return Field(
        default_factory=_layout_factory(layout),
        title=title,
        description=description,
        json_schema_extra={
            "group": GroupParameterCategory.PROPERTY.value,
            "editable": False,
            "creation_editable": True,
        },
    )


def _stator_field(layout: ValvePortLayout):
    return _mode_field(
        layout,
        title="Valve stator ports",
        description="External stator port layout for the valve body.",
    )


def _rotor_field(layout: ValvePortLayout):
    return _mode_field(
        layout,
        title="Valve rotor ports",
        description="Rotor channel layout used to derive possible connections.",
    )


@dataclass
class ThreePortTwoPositionValveData(ValveComponentData):
    stator_ports: ValvePortLayout = field(
        default_factory=_layout_factory(THREE_PORT_TWO_POSITION_STATOR)
    )
    rotor_ports: ValvePortLayout = field(
        default_factory=_layout_factory(THREE_PORT_TWO_POSITION_ROTOR)
    )


class ThreePortTwoPositionValveMode(ValveMode):
    stator_ports: ValvePortLayout = _stator_field(THREE_PORT_TWO_POSITION_STATOR)
    rotor_ports: ValvePortLayout = _rotor_field(THREE_PORT_TWO_POSITION_ROTOR)


@dataclass
class ThreePortFourPositionValveData(ValveComponentData):
    stator_ports: ValvePortLayout = field(
        default_factory=_layout_factory(THREE_PORT_FOUR_POSITION_STATOR)
    )
    rotor_ports: ValvePortLayout = field(
        default_factory=_layout_factory(THREE_PORT_FOUR_POSITION_ROTOR)
    )


class ThreePortFourPositionValveMode(ValveMode):
    stator_ports: ValvePortLayout = _stator_field(THREE_PORT_FOUR_POSITION_STATOR)
    rotor_ports: ValvePortLayout = _rotor_field(THREE_PORT_FOUR_POSITION_ROTOR)


@dataclass
class FourPortFivePositionValveData(ValveComponentData):
    stator_ports: ValvePortLayout = field(
        default_factory=_layout_factory(FOUR_PORT_FIVE_POSITION_STATOR)
    )
    rotor_ports: ValvePortLayout = field(
        default_factory=_layout_factory(FOUR_PORT_FIVE_POSITION_ROTOR)
    )


class FourPortFivePositionValveMode(ValveMode):
    stator_ports: ValvePortLayout = _stator_field(FOUR_PORT_FIVE_POSITION_STATOR)
    rotor_ports: ValvePortLayout = _rotor_field(FOUR_PORT_FIVE_POSITION_ROTOR)


@dataclass
class SixPortTwoPositionValveData(ValveComponentData):
    stator_ports: ValvePortLayout = field(
        default_factory=_layout_factory(SIX_PORT_TWO_POSITION_STATOR)
    )
    rotor_ports: ValvePortLayout = field(
        default_factory=_layout_factory(SIX_PORT_TWO_POSITION_ROTOR)
    )


class SixPortTwoPositionValveMode(ValveMode):
    stator_ports: ValvePortLayout = _stator_field(SIX_PORT_TWO_POSITION_STATOR)
    rotor_ports: ValvePortLayout = _rotor_field(SIX_PORT_TWO_POSITION_ROTOR)


@dataclass
class TwoPortDistributionValveData(ValveComponentData):
    stator_ports: ValvePortLayout = field(
        default_factory=_layout_factory(TWO_PORT_DISTRIBUTION_STATOR)
    )
    rotor_ports: ValvePortLayout = field(
        default_factory=_layout_factory(TWO_PORT_DISTRIBUTION_ROTOR)
    )


class TwoPortDistributionValveMode(ValveMode):
    stator_ports: ValvePortLayout = _stator_field(TWO_PORT_DISTRIBUTION_STATOR)
    rotor_ports: ValvePortLayout = _rotor_field(TWO_PORT_DISTRIBUTION_ROTOR)


@dataclass
class FourPortDistributionValveData(ValveComponentData):
    stator_ports: ValvePortLayout = field(
        default_factory=_layout_factory(FOUR_PORT_DISTRIBUTION_STATOR)
    )
    rotor_ports: ValvePortLayout = field(
        default_factory=_layout_factory(FOUR_PORT_DISTRIBUTION_ROTOR)
    )


class FourPortDistributionValveMode(ValveMode):
    stator_ports: ValvePortLayout = _stator_field(FOUR_PORT_DISTRIBUTION_STATOR)
    rotor_ports: ValvePortLayout = _rotor_field(FOUR_PORT_DISTRIBUTION_ROTOR)


@dataclass
class SixPortDistributionValveData(ValveComponentData):
    stator_ports: ValvePortLayout = field(
        default_factory=_layout_factory(SIX_PORT_DISTRIBUTION_STATOR)
    )
    rotor_ports: ValvePortLayout = field(
        default_factory=_layout_factory(SIX_PORT_DISTRIBUTION_ROTOR)
    )


class SixPortDistributionValveMode(ValveMode):
    stator_ports: ValvePortLayout = _stator_field(SIX_PORT_DISTRIBUTION_STATOR)
    rotor_ports: ValvePortLayout = _rotor_field(SIX_PORT_DISTRIBUTION_ROTOR)


@dataclass
class TwelvePortDistributionValveData(ValveComponentData):
    stator_ports: ValvePortLayout = field(
        default_factory=_layout_factory(TWELVE_PORT_DISTRIBUTION_STATOR)
    )
    rotor_ports: ValvePortLayout = field(
        default_factory=_layout_factory(TWELVE_PORT_DISTRIBUTION_ROTOR)
    )


class TwelvePortDistributionValveMode(ValveMode):
    stator_ports: ValvePortLayout = _stator_field(TWELVE_PORT_DISTRIBUTION_STATOR)
    rotor_ports: ValvePortLayout = _rotor_field(TWELVE_PORT_DISTRIBUTION_ROTOR)


@dataclass
class SixteenPortDistributionValveData(ValveComponentData):
    stator_ports: ValvePortLayout = field(
        default_factory=_layout_factory(SIXTEEN_PORT_DISTRIBUTION_STATOR)
    )
    rotor_ports: ValvePortLayout = field(
        default_factory=_layout_factory(SIXTEEN_PORT_DISTRIBUTION_ROTOR)
    )


class SixteenPortDistributionValveMode(ValveMode):
    stator_ports: ValvePortLayout = _stator_field(SIXTEEN_PORT_DISTRIBUTION_STATOR)
    rotor_ports: ValvePortLayout = _rotor_field(SIXTEEN_PORT_DISTRIBUTION_ROTOR)
