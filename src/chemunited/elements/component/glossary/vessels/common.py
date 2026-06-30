from chemunited_core.components.internals import (
    DEFAULT_INVENTORY_KEY,
    VolumeContentBase,
)
from chemunited_core.compounds.registry import COMPOUNDS
from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QColor

from chemunited.elements.component.component_parts.scene_item import SceneItem


def _rgba_hex_to_qcolor(hex_str: str) -> QColor:
    h = hex_str.lstrip("#")
    return QColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(h[6:8], 16))


class FlaskContent(SceneItem):
    def __init__(self, width=40, height=40, parent=None) -> None:
        super().__init__(width=width, height=height, parent=parent)

    def boundingRect(self):
        return QRectF(-self.width / 2, -self.height / 2, self.width, self.height)

    def paint(self, painter, option, widget=None) -> None:
        painter.setPen(Qt.PenStyle.NoPen)  # type: ignore
        painter.setBrush(Qt.GlobalColor.blue)  # type: ignore
        painter.drawEllipse(self.boundingRect())  # type: ignore

    def content_color(self, iventory=DEFAULT_INVENTORY_KEY) -> QColor:
        if getattr(self.parent_ref, "inf", None) and getattr(
            self.parent_ref.inf, "internal_inventories", None  # type: ignore
        ):
            volume_content: VolumeContentBase
            for key, volume_content in self.parent_ref.inf.internal_inventories.items():  # type: ignore
                if key != iventory:
                    continue
                if volume_content.liq_content.volume > 0:  # type: ignore[attr-defined]
                    return _rgba_hex_to_qcolor(
                        COMPOUNDS.get_color(volume_content.liq_content)  # type: ignore[attr-defined]
                    )
                else:
                    return _rgba_hex_to_qcolor(
                        COMPOUNDS.get_color(volume_content.gas_content)  # type: ignore[attr-defined]
                    )
        return QColor(Qt.GlobalColor.transparent)
