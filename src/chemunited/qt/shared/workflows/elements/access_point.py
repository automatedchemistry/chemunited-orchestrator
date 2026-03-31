from typing import TYPE_CHECKING

from PyQt5.QtCore import QRectF
from PyQt5.QtGui import QColor, QPainter, QPainterPath
from PyQt5.QtWidgets import QGraphicsItem, QStyleOptionGraphicsItem, QWidget
from qfluentwidgets import isDarkTheme

from chemunited.shared.workflows.design import NodeState, get_node_color

if TYPE_CHECKING:
    from .work_node import WorkflowNode


class WorkflowAccessPoint(QGraphicsItem):
    """
    Represents a SINGLE connection point (circle) on a node.
    It can be independently hovered, clicked, and tracked.
    """

    def __init__(self, index: int, parent: "WorkflowAccessPoints"):
        super().__init__(parent)
        self.index = index
        self.group_ref = parent

        # Native Qt flag so this individual dot can be selected/highlighted later
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)

    @property
    def role(self) -> str:
        return self.group_ref.role

    @property
    def node(self) -> "WorkflowNode | None":
        return self.group_ref.node

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, 10, 10)

    def paint(
        self,
        painter: QPainter | None,
        option: QStyleOptionGraphicsItem | None,
        widget: QWidget | None = None,
    ) -> None:
        if painter is None:
            return
        # Highlight blue if the user selects this specific pin
        contour_color = (
            "#3A7AFE"
            if self.isSelected()
            else ("#646464" if isDarkTheme() else "#aaaaaa")
        )

        # Use the dynamic color from design.py mapping we created earlier
        fill_color = get_node_color(NodeState.WAITING)

        painter.setBrush(QColor(fill_color))
        painter.setPen(QColor(contour_color))
        painter.drawEllipse(0, 0, 10, 10)


class WorkflowAccessPoints(QGraphicsItem):
    """
    The visual container (rounded rectangle) that groups multiple WorkflowAccessPoint circles.
    """

    def __init__(
        self,
        count: int = 1,
        orientation: str = "vertical",
        role: str = "left",
        node: "WorkflowNode | None" = None,
    ):
        super().__init__()
        self.orientation = orientation
        self.role = role
        self.node = node

        # Make the container natively selectable
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)

        self.ports: list[WorkflowAccessPoint] = []
        self._count = 0
        self.set_count(count)

    @property
    def count(self) -> int:
        return self._count

    def set_count(self, count: int):
        new_count = max(1, count)
        if self._count == new_count:
            return

        self.prepareGeometryChange()

        # Clean up old port children
        for port in self.ports:
            port.setParentItem(None)
        self.ports.clear()

        self._count = new_count

        # Instantiate structural children
        for i in range(self._count):
            port = WorkflowAccessPoint(index=i, parent=self)
            self.ports.append(port)

        self._update_port_positions()
        self.update()

    def _update_port_positions(self):
        # Automatically distribute the child points across the container
        for i, port in enumerate(self.ports):
            if self.orientation == "vertical":
                y = 5 + self.height * i / self._count
                port.setPos(2.5, y)
            else:
                x = 5 + self.width * i / self._count
                port.setPos(x, 2.5)

    @property
    def width(self) -> int:
        return 15 if self.orientation == "vertical" else self._count * 20

    @property
    def height(self) -> int:
        return self._count * 20 if self.orientation == "vertical" else 15

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self.width, self.height)

    def set_selected(self, selected: bool):
        self.setSelected(selected)
        for port in self.ports:
            port.setSelected(selected)
        self.update()

    @property
    def can_start_connection(self) -> bool:
        return self.role != "left"

    @property
    def can_end_connection(self) -> bool:
        return self.role == "left"

    def paint(
        self,
        painter: QPainter | None,
        option: QStyleOptionGraphicsItem | None,
        widget: QWidget | None = None,
    ) -> None:
        if painter is None:
            return
        # Determine theme colors dynamically (replacing the global strings)
        contour_color = (
            "#3A7AFE"
            if self.isSelected()
            else ("#646464" if isDarkTheme() else "#aaaaaa")
        )
        solid_color = "#2d2d2d" if isDarkTheme() else "#e5e5e5"

        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width, self.height, 3, 3)

        painter.setBrush(QColor(solid_color))
        painter.setPen(QColor(contour_color))
        painter.drawPath(path)
