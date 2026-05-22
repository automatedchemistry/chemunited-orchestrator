from typing import ClassVar

from chemunited.core.figure_registry.pipes import SourceData, SourceMode
from chemunited.qt.elements.component.graph_item import GraphComponent


class Source(GraphComponent[SourceData]):
    METADATA: ClassVar[type[SourceData]] = SourceData
    BASEMODE: ClassVar[type[SourceMode]] = SourceMode
    SVG_SCALE: ClassVar[float] = 1.0

    def build(self, svg_path: str | None = None) -> None:
        self._data.ports_by_number[1].relative_position = (20, 0)
        super().build(svg_path=":/components_icons/components/SourceSink.svg")
        self._svg.setRotation(180)
