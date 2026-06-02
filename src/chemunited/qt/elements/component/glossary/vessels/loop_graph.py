from typing import ClassVar

from PyQt5.QtCore import QPointF
from PyQt5.QtGui import QColor, QPainterPath, QPolygonF

from chemunited_core.common.constant import PATTERN_DIMENSION
from chemunited_core.components import PlugFlowComponentData, PlugFlowMode
from chemunited.qt.elements.component.graph_item import GraphComponent
from chemunited.qt.shared.graph_objects.custom_path import PathElementItem
from chemunited.qt.utils.math_functions import spring


class PathSpring(PathElementItem):

    DEFAULT_COLOR = QColor("#000000")
    DEFAULT_LINE_WIDTH = 5.0
    LENGTH = PATTERN_DIMENSION * 2
    COILS = 2
    WIDTH = PATTERN_DIMENSION

    def __init__(self, parent=None):

        super().__init__(parent=parent)

    def rebuild_path(self):
        x_coords, y_coords = spring(
            start_pos=(0, 0),
            length=self.LENGTH,
            coils=self.COILS,
            width=self.WIDTH,
        )
        # Build the path without Python loops (use a polygon)
        poly = QPolygonF(
            QPointF(float(x), float(y)) for x, y in zip(x_coords, y_coords)
        )
        path = QPainterPath()
        path.addPolygon(poly)
        self.setPath(path)


class PathFluidSpring(PathSpring):
    DEFAULT_COLOR = QColor("#E8E8E8")
    DEFAULT_LINE_WIDTH = 2


class Loop(GraphComponent[PlugFlowComponentData]):
    METADATA: ClassVar[type[PlugFlowComponentData]] = PlugFlowComponentData
    BASEMODE: ClassVar[type[PlugFlowMode]] = PlugFlowMode

    def build(self, svg_path: str | None = None) -> None:
        self._data.ports_by_number[1].relative_position = (-50, -5)
        self._data.ports_by_number[2].relative_position = (50, -5)

        self.tubing = PathSpring(parent=self)
        self.tubing.rebuild_path()
        self.tubing.moveBy(-50, -55)
        self.addToGroup(self.tubing)

        self.fluid_path = PathFluidSpring(parent=self)
        self.fluid_path.rebuild_path()
        self.fluid_path.moveBy(-50, -55)
        self.addToGroup(self.fluid_path)

        super().build(svg_path=":/components_icons/components/LoopBase.svg")
