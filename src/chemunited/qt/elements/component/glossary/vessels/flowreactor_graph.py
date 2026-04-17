from typing import ClassVar
from PyQt5.QtCore import QPointF
from PyQt5.QtGui import QColor, QPainterPath, QPolygonF
from pydantic import Field

from chemunited.core.components import PlugFlowComponentData, PlugFlowMode
from chemunited.qt.elements.component.graph_item import GraphComponent
from chemunited.qt.utils.math_functions import build_snake_path
from chemunited.qt.shared.graph_objects.custom_path import PathElementItem
from chemunited.core.common.enums import GroupParameterCategory
from chemunited.core.common.constant import PATTERN_DIMENSION
from chemunited.qt.elements.component.component_parts import SvgLayer



class FlowReactorMode(PlugFlowMode):
    heat_exchange: bool = Field(
        default=True,
        title="Heat Exchange",
        description="Whether the component allows heat exchange.",
        json_schema_extra={
            "group": GroupParameterCategory.PROPERTY.value,
            "editable": False,
            "lock_reason": "Internal Chosen",
        },
    )


class FlowReactorData(PlugFlowComponentData):
    heat_exchange: bool = True


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
        poly = QPolygonF(QPointF(float(x), float(y)) for x, y in zip(points[0], points[1]))
        path = QPainterPath()
        path.addPolygon(poly)
        self.setPath(path)


class PathFluid(PathTubing):
    DEFAULT_COLOR = QColor("#E8E8E8")
    DEFAULT_LINE_WIDTH = 2.0


class FlowReactor(GraphComponent[FlowReactorData]):
    METADATA: ClassVar[type[FlowReactorData]] = FlowReactorData
    BASEMODE: ClassVar[type[FlowReactorMode]] = FlowReactorMode

    def build(self, svg_path: str | None = None) -> None:

        if self._data.heat_exchange:
            jacket_svg_path = f":/components_icons/components/FlaskJacket.svg"
            self._svg_jacket = SvgLayer(
                jacket_svg_path,
                angle=self._data.angle + 90,
                scale=PATTERN_DIMENSION * self.SVG_SCALE,
                parent=self,
            )
            self.addToGroup(self._svg_jacket)

        self._data.ports_by_number[1].relative_position = (-45, -20)
        self._data.ports_by_number[2].relative_position = (45, -20)
        super().build(svg_path=f":/components_icons/components/FlowReactorBase.svg")
        self.tubing = PathTubing(parent=self)
        self.tubing.rebuild_path()
        self.tubing.moveBy(-42, -20)
        self.addToGroup(self.tubing)

        self.fluid_path = PathFluid(parent=self)
        self.fluid_path.rebuild_path()
        self.fluid_path.moveBy(-42, -20)
        self.addToGroup(self.fluid_path)


class PhotoReactor(FlowReactor):

    def build(self, svg_path: str | None = None) -> None:
        super().build()
        self.leds = SvgLayer(
            f":/components_icons/components/PhotoLeds.svg",
            angle=self._data.angle,
            scale=int(PATTERN_DIMENSION * self.SVG_SCALE * 0.5),
            parent=self,
        )
        self.leds.moveBy(0, -40)
        self.addToGroup(self.leds)
    

        
        