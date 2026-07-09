from typing import ClassVar

from chemunited_core.common.constant import PATTERN_DIMENSION
from chemunited_core.figure_registry import SyringePumpData, get_figure_path

from chemunited.elements.component.component_parts import StatusOverlay
from chemunited.elements.component.component_parts.svg_layer import SvgLayer
from chemunited.elements.component.graph_item import GraphComponent


class SyringePump(GraphComponent[SyringePumpData]):
    FIGURE: ClassVar[str] = "SyringePump"

    def build(self) -> None:
        try:
            plunger_bytes = get_figure_path("SyringePlunger").read_bytes()
            self._syringe_plunger = SvgLayer.from_bytes(
                plunger_bytes,
                scale=PATTERN_DIMENSION * 1.2,
                parent=self,
            )
            self._syringe_plunger.moveBy(2.5, 11.5)
            self.addToGroup(self._syringe_plunger)
        except (FileNotFoundError, OSError):
            pass
        super().build()

    def sync_visuals(self) -> None:
        # No fill-level geometry to derive from state yet — flow_rate is the
        # only field pump commands actually mutate, so a run/idle tint is the
        # honest signal we can give here.
        active = self._data.flow_rate_si != 0.0
        self._overlay.set_status(
            StatusOverlay.COLOR_ACTIVE if active else StatusOverlay.COLOR_IDLE
        )
        self._overlay.setVisible(active)
