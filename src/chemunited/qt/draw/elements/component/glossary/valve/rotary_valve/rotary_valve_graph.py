from chemunited.core.components.glossary.rotary_valve import ValveComponentData, ValvePortLayout
from chemunited.qt.shared.elements.component.graph_item import GraphComponent
from dataclasses import dataclass, field
from typing import ClassVar, Generic, TypeVar

ValveT = TypeVar("ValveT", bound=ValveComponentData)


class RotaryValveGraph(GraphComponent[ValveT], Generic[ValveT]):
    SVG_SCALE: ClassVar[float] = 3.0


@dataclass
class ThreePortTwoPositionValveData(ValveComponentData):
    stator_ports: ValvePortLayout = field(default_factory=lambda: [(None, 1, 2, 3), (0,)])
    rotor_ports: ValvePortLayout = field(default_factory=lambda: [(4, 4, None, None), (None,)])


class ThreePortTwoPositionValve(RotaryValveGraph[ThreePortTwoPositionValveData]):
    METADATA: ClassVar[type[ThreePortTwoPositionValveData]] = ThreePortTwoPositionValveData

@dataclass
class ThreePortFourPositionValveData(ValveComponentData):
    stator_ports: ValvePortLayout = field(default_factory=lambda: [(None, 1, 2, 3), (0,)])
    rotor_ports: ValvePortLayout = field(default_factory=lambda: [(4, 4, 5, 5), (4,)])


class ThreePortFourPositionValve(RotaryValveGraph[ThreePortFourPositionValveData]):
    METADATA: ClassVar[type[ThreePortFourPositionValveData]] = ThreePortFourPositionValveData

@dataclass
class FourPortFivePositionValveData(ValveComponentData):
    stator_ports: ValvePortLayout = field(default_factory=lambda:[
            (
                None,
                None,
                1,
                None,
                2,
                None,
                3,
                None,
            ),
            (0,),
        ]    
    )
    rotor_ports: ValvePortLayout = field(default_factory=lambda: [(None, 5, None, None, 4, None, 4, None), (5,)])


class FourPortFivePositionValve(RotaryValveGraph[FourPortFivePositionValveData]):
    METADATA: ClassVar[type[FourPortFivePositionValveData]] = FourPortFivePositionValveData


@dataclass
class SixPortTwoPositionValveData(ValveComponentData):
    stator_ports: ValvePortLayout = field(default_factory=lambda: [(1, 2, 3, 4, 5, 6), (0,)])
    rotor_ports: ValvePortLayout = field(default_factory=lambda: [(7, 7, 8, 8, 9, 9), (None,)])


class SixPortTwoPositionValve(RotaryValveGraph[SixPortTwoPositionValveData]):
    METADATA: ClassVar[type[SixPortTwoPositionValveData]] = SixPortTwoPositionValveData


# Distribution valve

@dataclass
class TwoPortDistributionValveData(ValveComponentData):
    stator_ports: ValvePortLayout = field(default_factory=lambda: [(1, 2), (0,)])
    rotor_ports: ValvePortLayout = field(default_factory=lambda: [(3, None), (3,)])


class TwoPortDistributionValve(RotaryValveGraph[TwoPortDistributionValveData]):
    METADATA: ClassVar[type[TwoPortDistributionValveData]] = TwoPortDistributionValveData


@dataclass
class FourPortDistributionValveData(ValveComponentData):
    stator_ports: ValvePortLayout = field(default_factory=lambda: [(1, 2, 3, 4), (0,)])
    rotor_ports: ValvePortLayout = field(default_factory=lambda: [(5, None, None, None), (5,)])


class FourPortDistributionValve(RotaryValveGraph[FourPortDistributionValveData]):
    METADATA: ClassVar[type[FourPortDistributionValveData]] = FourPortDistributionValveData


@dataclass
class SixPortDistributionValveData(ValveComponentData):
    stator_ports: ValvePortLayout = field(default_factory=lambda: [(1, 2, 3, 4, 5, 6), (0,)])
    rotor_ports: ValvePortLayout = field(default_factory=lambda: [(7, None, None, None, None, None), (7,)])


class SixPortDistributionValve(RotaryValveGraph[SixPortDistributionValveData]):
    METADATA: ClassVar[type[SixPortDistributionValveData]] = SixPortDistributionValveData


@dataclass
class TwelvePortDistributionValveData(ValveComponentData):
    stator_ports: ValvePortLayout = field(default_factory=lambda: [(1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12), (0,)])
    rotor_ports: ValvePortLayout = field(default_factory=lambda: [(13, None, None, None, None, None, None, None, None, None, None, None), (13,)])


class TwelvePortDistributionValve(RotaryValveGraph[TwelvePortDistributionValveData]):
    METADATA: ClassVar[type[TwelvePortDistributionValveData]] = TwelvePortDistributionValveData


@dataclass
class SixteenPortDistributionValveData(ValveComponentData):
    stator_ports: ValvePortLayout = field(default_factory=lambda: [(1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16), (0,)])
    rotor_ports: ValvePortLayout = field(default_factory=lambda: [(17, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None), (17,)])


class SixteenPortDistributionValve(RotaryValveGraph[SixteenPortDistributionValveData]):
    METADATA: ClassVar[type[SixteenPortDistributionValveData]] = SixteenPortDistributionValveData
