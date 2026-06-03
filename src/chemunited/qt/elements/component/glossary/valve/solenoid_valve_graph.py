from typing import ClassVar

from chemunited_core.figure_registry.solenoid_valve import (
    Solenoid2WayValveMode,
    SolenoidValve2WayData,
    SolenoidValveData,
    SolenoidValveMode,
)
from chemunited.qt.elements.component.graph_item import GraphComponent


class SolenoidValve(GraphComponent[SolenoidValveData]):
    METADATA: ClassVar[type[SolenoidValveData]] = SolenoidValveData
    BASEMODE: ClassVar[type[SolenoidValveMode]] = SolenoidValveMode
    SVG_SCALE: ClassVar[float] = 1.0


class SolenoidValve2Way(GraphComponent[SolenoidValve2WayData]):
    METADATA: ClassVar[type[SolenoidValve2WayData]] = SolenoidValve2WayData
    BASEMODE: ClassVar[type[Solenoid2WayValveMode]] = Solenoid2WayValveMode
    SVG_SCALE: ClassVar[float] = 1.0
