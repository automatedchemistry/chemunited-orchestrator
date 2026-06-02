from typing import ClassVar

from chemunited_core.components import (
    BackPressureRegulatorData,
    BackPressureRegulatorMode,
)
from chemunited.qt.elements.component.graph_item import GraphComponent


class BackPressureRegulator(GraphComponent[BackPressureRegulatorData]):
    METADATA: ClassVar[type[BackPressureRegulatorData]] = BackPressureRegulatorData
    BASEMODE: ClassVar[type[BackPressureRegulatorMode]] = BackPressureRegulatorMode

    def build(self, svg_path: str | None = None) -> None:
        self._data.ports_by_number[1].relative_position = (-50, 28)
        self._data.ports_by_number[2].relative_position = (50, 28)
        return super().build(
            svg_path=":/components_icons/components/BackPressureRegulator.svg"
        )
