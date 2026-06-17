from PyQt5.QtCore import QRectF, Qt, Qt
from PyQt5.QtCore import QRectF
from PyQt5.QtGui import QColor
from chemunited.elements.component.component_parts.scene_item import SceneItem

from chemunited_core.compounds.registry import COMPOUNDS
from chemunited_core.components.internals import VolumeContentBase


class FlaskContent(SceneItem):
    def __init__(self, width=40, height=40, parent=None) -> None:
        super().__init__(width=width, height=height, parent=parent)

    def boundingRect(self):
        return QRectF(-self.width/2, -self.height/2, self.width, self.height)

    def paint(self, painter, option, widget=None) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(Qt.GlobalColor.blue)
        painter.drawEllipse(self.boundingRect())
    
    def content_color(self) -> QColor:
        if getattr(self.parent_ref, 'inf', None) and getattr(self.parent_ref.inf, 'internal_inventories', None):
            volume_content: VolumeContentBase
            for volume_content in self.parent_ref.inf.internal_inventories.values():
                if volume_content.liq_content.volume > 0:
                    return QColor(COMPOUNDS.get_color(volume_content.liq_content))
                else:
                    return QColor(COMPOUNDS.get_color(volume_content.gas_content))
        return QColor(Qt.transparent)