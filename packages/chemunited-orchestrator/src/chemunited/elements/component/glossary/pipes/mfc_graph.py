from typing import ClassVar

from chemunited_core.figure_registry import MFCComponentData

from chemunited.elements.component.component_parts import StatusOverlay
from chemunited.elements.component.graph_item import GraphComponent


class MFCComponent(GraphComponent[MFCComponentData]):
    FIGURE: ClassVar[str] = "MFCComponent"

    def build(self) -> None:
        super().build()
        self.sync_visuals()

    def sync_visuals(self) -> None:
        active = self._data.flowrate_si > 0.0
        self._overlay.set_status(
            StatusOverlay.COLOR_ACTIVE if active else StatusOverlay.COLOR_IDLE
        )
        self._overlay.setVisible(True)
