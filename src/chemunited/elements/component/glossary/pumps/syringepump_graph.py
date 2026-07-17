from typing import ClassVar

from chemunited_core.common.constant import PATTERN_DIMENSION
from chemunited_core.figure_registry import SyringePumpData, get_figure_path
from PyQt5.QtCore import QRectF, Qt

from chemunited.elements.component.component_parts import StatusOverlay
from chemunited.elements.component.component_parts.svg_layer import SvgLayer
from chemunited.elements.component.glossary.vessels.common import FlaskContent
from chemunited.elements.component.graph_item import GraphComponent


def _get_fill_level(component_data: SyringePumpData) -> float:
    fill = 0.0
    inventories = getattr(component_data, "internal_inventories", {})
    inventory = next(iter(inventories.values()), None)
    syringe_volume = getattr(component_data, "syringe_volume", None)
    capacity = (
        float(syringe_volume.to_base_units().magnitude) if syringe_volume else 0.0
    )
    if inventory is not None and capacity > 0:
        fill = inventory.liq_content.volume / capacity
        fill = max(0.0, min(1.0, fill))
    return fill


class SyringePumpContent(FlaskContent):
    def paint(self, painter, option, widget=None) -> None:
        color = self.content_color()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)

        fill = _get_fill_level(getattr(self.parent_ref, "inf", None))

        rect = QRectF(
            0,
            0,
            self.width * fill,
            self.height,
        )
        painter.drawRoundedRect(rect, 3, 3)


class SyringePump(GraphComponent[SyringePumpData]):
    FIGURE: ClassVar[str] = "SyringePump"
    plunger_x_empty = 2.5
    plunger_dx_full = PATTERN_DIMENSION - 3.5
    plunger_y = 11.5

    def build(self) -> None:
        try:
            self._syringe_content = SyringePumpContent(
                width=int(PATTERN_DIMENSION * self.SVG_SCALE * 0.5),
                height=int(PATTERN_DIMENSION * self.SVG_SCALE * 0.1),
                parent=self,
            )
            self._syringe_content.moveBy(-27.5, 6.2)
            self.addToGroup(self._syringe_content)
            plunger_bytes = get_figure_path("SyringePlunger").read_bytes()
            self._syringe_plunger = SvgLayer.from_bytes(
                plunger_bytes,
                scale=PATTERN_DIMENSION * 1.2,
                parent=self,
            )
            # addToGroup() re-anchors the child's local position to account for
            # the group's own bounding-rect bookkeeping, on top of the centering
            # SvgLayer already applied to itself - so the stable baseline to
            # offset from only exists *after* addToGroup(), not before it.
            self.addToGroup(self._syringe_plunger)
            self._plunger_base_pos = self._syringe_plunger.pos()
            self._syringe_plunger.setPos(
                self._plunger_base_pos.x() + self.plunger_x_empty,
                self._plunger_base_pos.y() + self.plunger_y,
            )
        except (FileNotFoundError, OSError):
            pass
        super().build()

    def sync_visuals(self) -> None:
        fill = _get_fill_level(self._data)
        self._syringe_plunger.setPos(
            self._plunger_base_pos.x()
            + self.plunger_x_empty
            + self.plunger_dx_full * fill,
            self._plunger_base_pos.y() + self.plunger_y,
        )
        self._syringe_content.update()

        active = self._data.flow_rate_si != 0.0
        self._overlay.set_status(
            StatusOverlay.COLOR_ACTIVE if active else StatusOverlay.COLOR_IDLE
        )
        self._overlay.setVisible(active)
