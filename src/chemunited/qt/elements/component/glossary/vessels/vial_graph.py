from typing import ClassVar

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QFont, QPen

from chemunited.core.figure_registry.vessels import VialData, VialMode
from chemunited.qt.elements.component.component_parts import SceneItem, SvgLayer
from chemunited.qt.elements.component.graph_item import GraphComponent
from chemunited.qt.utils.math_functions import position_to_letter

CELL_SIZE = 40
ROW_HEADER_WIDTH = 12
COLUMN_HEADER_HEIGHT = 12
VIAL_ICON_SCALE = 0.75
TRAY_LABEL_PIXEL_SIZE = 8


def _tray_dimensions(columns: int, rows: int) -> tuple[int, int]:
    return (
        ROW_HEADER_WIDTH + columns * CELL_SIZE,
        rows * CELL_SIZE + COLUMN_HEADER_HEIGHT,
    )


def _tray_origin(columns: int, rows: int) -> tuple[float, float]:
    width, height = _tray_dimensions(columns, rows)
    return -width / 2, -height / 2


def _well_center(
    row_index: int,
    column_index: int,
    columns: int,
    rows: int,
    y_offset: float = 0,
) -> tuple[float, float]:
    left, top = _tray_origin(columns, rows)
    return (
        left + ROW_HEADER_WIDTH + column_index * CELL_SIZE + CELL_SIZE / 2,
        top + row_index * CELL_SIZE + (CELL_SIZE - y_offset) / 2,
    )


class FramePanel(SceneItem):
    def __init__(self, data: VialData, parent=None):
        width, height = _tray_dimensions(data.column, data.row)
        super().__init__(
            width=width,
            height=height,
            parent=parent,
        )
        self._data = data

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(painter.Antialiasing, True)
        contour_color = QColor("#000000")
        grid_color = QColor("#BFC7D1")

        left = -self.width / 2
        top = -self.height / 2
        well_left = left + ROW_HEADER_WIDTH
        well_top = top
        well_width = self._data.column * CELL_SIZE
        well_height = self._data.row * CELL_SIZE
        column_header_top = well_top + well_height

        painter.setPen(QPen(contour_color, 2))
        painter.setBrush(Qt.transparent)
        painter.drawRoundedRect(
            QRectF(well_left, well_top, well_width, well_height),
            3,
            3,
        )

        painter.setBrush(Qt.transparent)  # type: ignore[attr-defined]
        painter.setPen(QPen(contour_color, 1))
        painter.drawRoundedRect(
            QRectF(left, well_top, ROW_HEADER_WIDTH, well_height),
            3,
            3,
        )
        painter.drawRoundedRect(
            QRectF(well_left, column_header_top, well_width, COLUMN_HEADER_HEIGHT),
            3,
            3,
        )

        painter.setPen(QPen(grid_color, 1))
        for column_index in range(1, self._data.column):
            x_position = well_left + column_index * CELL_SIZE
            painter.drawLine(
                QPointF(x_position, well_top),
                QPointF(x_position, well_top + well_height),
            )
        for row_index in range(1, self._data.row):
            y_position = well_top + row_index * CELL_SIZE
            painter.drawLine(
                QPointF(well_left, y_position),
                QPointF(well_left + well_width, y_position),
            )

        label_font = QFont(painter.font())
        label_font.setPixelSize(TRAY_LABEL_PIXEL_SIZE)
        painter.setFont(label_font)
        painter.setPen(QPen(contour_color, 1))
        for row_index in range(self._data.row):
            painter.drawText(
                QRectF(
                    left,
                    well_top + row_index * CELL_SIZE,
                    ROW_HEADER_WIDTH,
                    CELL_SIZE,
                ),
                Qt.AlignCenter,
                position_to_letter(row_index + 1),
            )

        for column_index in range(self._data.column):
            painter.drawText(
                QRectF(
                    well_left + column_index * CELL_SIZE,
                    column_header_top,
                    CELL_SIZE,
                    COLUMN_HEADER_HEIGHT,
                ),
                Qt.AlignCenter,
                str(column_index + 1),
            )


class Vial(GraphComponent[VialData]):
    METADATA: ClassVar[type[VialData]] = VialData
    BASEMODE: ClassVar[type[VialMode]] = VialMode

    def build(self, svg_path: str | None = None) -> None:
        if not self._data.is_array:
            if 1 in self._data.ports_by_number:
                self._data.ports_by_number[1].relative_position = (0, -11)
            if 2 in self._data.ports_by_number:
                self._data.ports_by_number[2].relative_position = (0, 10)
            super().build(svg_path)
            return

        self._svg = FramePanel(self._data, self)
        self.addToGroup(self._svg)
        for row_index in range(self._data.row):
            for column_index in range(self._data.column):
                vial_svg_path = ":/components_icons/components/Vial.svg"
                vial_graph = SvgLayer(
                    svg_path=vial_svg_path,
                    scale=VIAL_ICON_SCALE * CELL_SIZE,
                    parent=self,
                )
                center_x, center_y = _well_center(
                    row_index,
                    column_index,
                    self._data.column,
                    self._data.row,
                )
                centered_offset = vial_graph.pos()
                vial_graph.setPos(
                    centered_offset.x() + center_x,
                    centered_offset.y() + center_y,
                )
                self.addToGroup(vial_graph)

        self.build_connections_points()

        self.build_labels_and_flags()
