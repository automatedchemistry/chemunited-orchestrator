from typing import ClassVar

from chemunited_core.common.constant import PATTERN_DIMENSION
from chemunited_core.figure_registry import get_figure_path
from chemunited_core.figure_registry.vessels import (
    FlowReactorData,
)
from PyQt5.QtCore import QPointF
from PyQt5.QtGui import QColor, QPainterPath, QPolygonF

from chemunited.elements.component.component_parts import SvgLayer
from chemunited.elements.component.graph_item import GraphComponent
from chemunited.shared.graph_objects.custom_path import PathElementItem
from chemunited.utils.math_functions import build_snake_path


class PathTubing(PathElementItem):
    DEFAULT_COLOR = QColor("#000000")
    DEFAULT_LINE_WIDTH = 5.0
    RADIUS = 3
    LENGTH = 40
    N_CIRCLE = 15

    def __init__(self, parent=None):

        super().__init__(parent=parent)

    def rebuild_path(self):
        points, start, end = build_snake_path(
            radius=self.RADIUS,
            length=self.LENGTH,
            n_circle=self.N_CIRCLE,
        )
        # Build the path without Python loops (use a polygon)
        poly = QPolygonF(
            QPointF(float(x), float(y)) for x, y in zip(points[0], points[1])
        )
        path = QPainterPath()
        path.addPolygon(poly)
        self.setPath(path)


class PathFluid(PathTubing):
    DEFAULT_COLOR = QColor("#E8E8E8")
    DEFAULT_LINE_WIDTH = 2.0


class FlowReactor(GraphComponent[FlowReactorData]):
    FIGURE: ClassVar[str] = "FlowReactor"

    def build(self) -> None:
        if self._data.heat_exchange:
            self._svg_jacket = SvgLayer.from_bytes(
                get_figure_path("FlaskJacket").read_bytes(),
                scale=PATTERN_DIMENSION * self.SVG_SCALE,
                parent=self,
            )
            self._svg_jacket.setRotation(90)
            self.addToGroup(self._svg_jacket)

        super().build()
        self.tubing = PathTubing(parent=self)
        self.tubing.rebuild_path()
        self.tubing.moveBy(-42, -20)
        self.addToGroup(self.tubing)

        self.fluid_path = PathFluid(parent=self)
        self.fluid_path.rebuild_path()
        self.fluid_path.moveBy(-42, -20)
        self.addToGroup(self.fluid_path)


class PhotoReactor(FlowReactor):
    FIGURE: ClassVar[str] = "PhotoReactor"

    def build(self) -> None:
        super().build()
        self.leds = SvgLayer.from_bytes(
            get_figure_path("PhotoLeds").read_bytes(),
            scale=int(PATTERN_DIMENSION * self.SVG_SCALE * 0.5),
            parent=self,
        )
        self.leds.moveBy(0, -40)
        self.addToGroup(self.leds)
