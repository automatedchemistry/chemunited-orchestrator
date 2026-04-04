from typing import ClassVar

from chemunited.core.components import (
    BackPressureRegulatorData,
    BackPressureRegulatorMode,
)
from chemunited.qt.draw.elements.component.graph_item import GraphComponent


class BackPressureRegulator(GraphComponent[BackPressureRegulatorData]):
    METADATA: ClassVar[type[BackPressureRegulatorData]] = BackPressureRegulatorData
    BASEMODE: ClassVar[type[BackPressureRegulatorMode]] = BackPressureRegulatorMode
