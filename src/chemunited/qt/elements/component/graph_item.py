"""GraphComponent — visual representation of a ComponentData in the platform scene.

Responsibilities:
  - Wrap child scene items (SvgLayer, ConnectionPoints, TextElements, badges,
    warning, overlay) into a single QGraphicsItemGroup.
  - Expose a thin public API (sync, set_frame_mode, set_online, show_warning,
    highlight) so that scene controllers never need to reach inside.
  - Forward position-change notifications to each ConnectionPoint so that
    connected edges can redraw themselves.

NOT responsible for:
  - Routing logic or graph topology (GraphBuilder owns that).
  - Persisting state (ComponentData is the source of truth).
  - Theme management (delegated to each child item's paint method).
  - Creating or destroying connections between components.
"""

from __future__ import annotations

from dataclasses import asdict
from math import ceil
from pathlib import Path
from typing import ClassVar, Generic, TypeVar

from loguru import logger
from pydantic import BaseModel
from PyQt5.QtCore import QFile, QRectF, QSize, Qt
from PyQt5.QtGui import QColor, QPainter, QPen, QTransform
from PyQt5.QtSvg import QSvgGenerator
from PyQt5.QtWidgets import (
    QGraphicsDropShadowEffect,
    QGraphicsItem,
    QGraphicsItemGroup,
    QGraphicsRectItem,
    QStyleOptionGraphicsItem,
)
from qfluentwidgets import isDarkTheme

from chemunited.core.common.constant import PATTERN_DIMENSION
from chemunited.core.common.enums import ConnectionType as CoreConnectionType
from chemunited.core.components import ComponentData, ComponentMode
from chemunited.qt.elements.component.component_parts import (
    ConnectionPoint,
    ConnectivityBadge,
    ElectronicConnectionPoint,
    FlowConnectionPoint,
    HeatConnectionPoint,
    MoveConnectionPoint,
    StatusOverlay,
    SvgLayer,
    TextElement,
    WarningDisplay,
)
from chemunited.qt.shared.enums import SetupStepMode

# Maps chemunited_core ConnectionType values to their visual point classes.
# HYDRAULIC is the core counterpart of what the UI layer calls FLOW.
_POINT_FACTORY: dict[CoreConnectionType, type[ConnectionPoint]] = {
    CoreConnectionType.HYDRAULIC: FlowConnectionPoint,
    CoreConnectionType.HEAT: HeatConnectionPoint,
    CoreConnectionType.ELECTRONIC: ElectronicConnectionPoint,
    CoreConnectionType.MOVEMENT: MoveConnectionPoint,
}

# Radius used for FlowConnectionPoints (Heat/Electronic/Move derive their own
# radius internally from PATTERN_DIMENSION).
_FLOW_RADIUS: int = PATTERN_DIMENSION // 10


DataT = TypeVar("DataT", bound=ComponentData)


def _make_shadow(blur: int = 12, color: str = "#1E88E5") -> QGraphicsDropShadowEffect:
    """Return a pre-configured drop-shadow effect."""
    fx = QGraphicsDropShadowEffect()
    fx.setBlurRadius(blur)
    fx.setColor(QColor(color))
    fx.setOffset(0, 0)
    return fx


class GraphComponent(QGraphicsItemGroup, Generic[DataT]):
    """Visual representation of a ComponentData in the platform scene.

    Each instance is a QGraphicsItemGroup whose bounding rect is contributed
    to by the SVG figure, connection points, and port labels.  The component
    name, connectivity badge, warning badge, and status overlay are plain
    children (setParentItem) so they follow the group without inflating its
    bounding rect.

    Typical lifecycle::

        component = GraphComponent(data)
        scene.addItem(component)
        # later …
        component.sync(updated_data)
        component.set_frame_mode(SetupStepMode.CONNECTIVITY)

    Subclasses narrow the data type by declaring::

        class MyComponent(GraphComponent[MyData]):
            METADATA: ClassVar[type[MyData]] = MyData
            BASEMODE: ClassVar[type[MyMode]] = MyMode
            SVG_SCALE: ClassVar[float] = 2.0
    """

    METADATA: ClassVar[type[ComponentData]] = ComponentData
    BASEMODE: ClassVar[type[ComponentMode]] = (
        ComponentMode  # used by the property widget
    )
    SVG_SCALE: ClassVar[float] = 2.0

    def __init__(self, data: DataT) -> None:
        super().__init__()

        self._data: DataT = data
        self._mode: SetupStepMode = SetupStepMode.DESIGN
        self._deletable: bool = True
        self._warning_active: bool = False

        # ── group children (contribute to boundingRect) ────────────
        self._svg: SvgLayer | QGraphicsRectItem
        self._points: dict[int, ConnectionPoint] = {}
        self._port_labels: dict[int, TextElement] = {}

        # ── plain children (excluded from boundingRect) ────────────
        self._name: TextElement
        self._badge: ConnectivityBadge | None = None
        self._warning: WarningDisplay
        self._overlay: StatusOverlay
        self._bounding_rect: QGraphicsRectItem

        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)  # type: ignore
        self.setFlag(QGraphicsItem.ItemIsMovable, True)  # type: ignore
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)  # type: ignore
        self.setFiltersChildEvents(False)  # ports receive their own events
        self.setAcceptHoverEvents(True)  # needed for child hover to work

        self.build()
        self.post_layout()
        self.build_bounding_rect()
        self.setPos(*data.position)
        self.set_frame_mode(SetupStepMode.DESIGN)  # initialise badge/warning visibility

    # -- properties --

    @property
    def inf(self) -> DataT:
        return self._data

    @property
    def base_mode_instance(self) -> ComponentMode:
        data = asdict(self._data)
        mode_data = {
            name: value
            for name, value in data.items()
            if name in self.BASEMODE.model_fields
        }
        return self.BASEMODE.model_validate(mode_data)

    # ── construction ───────────────────────────────────────────────

    def build(self, svg_path: str | None = None) -> None:
        """Assemble all child items from ComponentData.

        Called once from __init__. Subclasses may override to implement
        a custom layout — call super().build() or fully replace it.
        """
        # SVG figure, or fallback rect when no SVG asset is available.
        if svg_path is None:
            svg_path = f":/components_icons/components/{self._data.figure}.svg"
        if QFile.exists(svg_path):
            self._svg = SvgLayer(
                svg_path,
                angle=self._data.angle,
                scale=PATTERN_DIMENSION * self.SVG_SCALE,
                parent=self,
            )
        else:
            logger.warning(
                f"Device doesn't have an SVG icon: {self._data.figure} - Not found in {svg_path}"
            )
            self._svg = QGraphicsRectItem(
                -PATTERN_DIMENSION / 2,
                -PATTERN_DIMENSION / 2,
                PATTERN_DIMENSION,
                PATTERN_DIMENSION,
                parent=self,
            )
        self.addToGroup(self._svg)

        # Connection points — one per port.
        for port_num, port in self._data.ports_by_number.items():
            cls = _POINT_FACTORY.get(port.category, FlowConnectionPoint)
            if cls is FlowConnectionPoint:
                point: ConnectionPoint = cls(
                    position=port.relative_position,
                    radius=_FLOW_RADIUS,
                    id_connection=str(port_num),
                    parent=self,
                )
            else:
                point = cls(
                    position=port.relative_position,
                    id_connection=str(port_num),
                    parent=self,
                )
            point.setZValue(1)
            self._points[port_num] = point
            self.addToGroup(point)

        # Port labels — positioned outward from the connection point.
        for port_num, port in self._data.ports_by_number.items():
            label = TextElement(str(port_num), parent=self)
            label.setPos(*port.relative_position)
            self._port_labels[port_num] = label
            label.setVisible(port.show_in_graph)
            self.addToGroup(label)

        # Plain children — follow the group but don't affect its bounding rect.
        self._name = TextElement(self._data.name, parent=self)

        if self._data.is_electronic:
            self._badge = ConnectivityBadge(
                dimension=PATTERN_DIMENSION // 3,
                parent=self,
            )
            self._badge.setVisible(False)

        self._warning = WarningDisplay(parent=self)
        self._warning.setVisible(False)

        self._overlay = StatusOverlay(dimension=PATTERN_DIMENSION, parent=self)
        self._overlay.setVisible(False)
        self.addToGroup(self._name)
        self.addToGroup(self._warning)
        self.addToGroup(self._overlay)

    def post_layout(self) -> None:
        """Position name, badge, warning, and overlay relative to the group boundingRect.

        Called once from __init__ after build(), and again from sync() when
        rotation changes invalidates the cached bounding rect.  Subclasses may
        override for a custom arrangement.
        """
        br = self.boundingRect()

        # Name: centred horizontally, placed below the figure with a 4 px gap.
        name_w = self._name.boundingRect().width()
        self._name.setPos(-name_w / 2, br.bottom() + 4)

        # Badge: centred horizontally, placed above the figure with a 4 px gap.
        if self._badge is not None:
            badge_br = self._badge.boundingRect()
            self._badge.setPos(
                -badge_br.width() / 2,
                br.top() - badge_br.height() - 4,
            )

        # Warning: to the left of the figure, vertically centred.
        warn_br = self._warning.boundingRect()
        self._warning.setPos(
            br.left() - warn_br.width() - 4,
            -warn_br.height() / 2,
        )

        # Overlay: centred over the figure.
        self._overlay.setPos(0, 0)

    def build_bounding_rect(self) -> None:
        self._bounding_rect = QGraphicsRectItem(self.boundingRect())
        self._bounding_rect.setParentItem(self)
        self._bounding_rect.setPen(QPen(Qt.black, 1))  # type: ignore
        self._bounding_rect.setBrush(Qt.transparent)  # type: ignore
        self._bounding_rect.setVisible(False)

    # ── public API ─────────────────────────────────────────────────

    def sync(self, mode: BaseModel) -> None:
        """Reconcile visuals when ComponentData is updated externally.

        Only position and angle are expected to change after construction.
        Rebuilding the full item tree on every sync would be wasteful.
        """
        self._data.update(mode)
        self.setPos(self._data.position[0], self._data.position[1])
        if isinstance(self._svg, SvgLayer):
            self._svg.update_angle(self._data.angle)
        else:
            self._svg.setRotation(self._data.angle)
        # Rotation changes the bounding rect, so re-position plain children.
        self.post_layout()

    def _restore_port_graph_visibility(self) -> None:
        """Apply each port's declared graph visibility to its point and label."""
        for port_num, port in self._data.ports_by_number.items():
            label = self._port_labels.get(port_num)
            if label is not None:
                label.setVisible(port.show_in_graph)

    def set_frame_mode(self, mode: SetupStepMode) -> None:
        """Configure visibility and interaction flags for the active editor frame.

        Visibility rules per mode:

        +--------------+---------+-----------+--------+-------------+-------+---------+
        | mode         | movable | deletable | points | port_labels | badge | warning |
        +==============+=========+===========+========+=============+=======+=========+
        | DESIGN       | yes     | yes       | yes    | yes         | no    | no      |
        | PROTOCOLS    | yes     | no        | yes    | yes         | no    | no      |
        | CONNECTIVITY | yes     | no        | no     | no          | yes   | active* |
        +--------------+---------+-----------+--------+-------------+-------+---------+

        *CONNECTIVITY: warning is shown only when show_warning(True) was previously called.
        """
        self._mode = mode

        if mode == SetupStepMode.DESIGN:
            self.setFlag(QGraphicsItem.ItemIsMovable, True)  # type: ignore
            self._deletable = True
            self._restore_port_graph_visibility()
            if self._badge is not None:
                self._badge.setVisible(False)
            self._warning.setVisible(False)

        elif mode == SetupStepMode.PROTOCOLS:
            self.setFlag(QGraphicsItem.ItemIsMovable, True)  # type: ignore
            self._deletable = False
            self._restore_port_graph_visibility()
            if self._badge is not None:
                self._badge.setVisible(False)
            self._warning.setVisible(False)

        elif mode == SetupStepMode.CONNECTIVITY:
            self.setFlag(QGraphicsItem.ItemIsMovable, True)  # type: ignore
            self._deletable = False
            for pt in self._points.values():
                pt.setVisible(False)
            for lbl in self._port_labels.values():
                lbl.setVisible(False)
            if self._badge is not None:
                self._badge.setVisible(True)
            # Respect the previously stored warning state — do not force visible.
            self._warning.setVisible(self._warning_active)

    def set_online(self, online: bool, api: str = "") -> None:
        """Drive the connectivity badge. Called by ConnectivityManager."""
        if self._badge is not None:
            self._badge.setStatus(online, api)

    def show_warning(self, visible: bool, message: str = "") -> None:
        """Drive the warning badge. Called by GraphBuilder or SimAdapter.

        Stores the active state so that set_frame_mode(CONNECTIVITY) can
        restore the correct visibility without forcing it visible itself.
        """
        self._warning_active = visible
        self._warning.show_warning(visible)

    def get_connection_point(self, port_num: int) -> ConnectionPoint:
        """Return the ConnectionPoint UI item for the given port number."""
        try:
            return self._points[port_num]
        except KeyError:
            raise KeyError(
                f"Port {port_num} not found on component '{self._data.name}'"
            )

    def highlight(self, active: bool) -> None:
        """Apply or remove a drop-shadow highlight on the SVG and connection points.

        Used to indicate selection or hover state.  Effects are applied only
        to group children (_svg, _points) — plain children are unaffected.
        """
        if active:
            self._svg.setGraphicsEffect(_make_shadow())
            for pt in self._points.values():
                pt.setGraphicsEffect(_make_shadow())
        else:
            self._svg.setGraphicsEffect(None)
            for pt in self._points.values():
                pt.setGraphicsEffect(None)

    def show_bounding_rect(self, visible: bool) -> None:
        self._bounding_rect.setVisible(visible)

    def export_svg(self, path: Path) -> None:
        """Export the component drawing to SVG without name or port-number labels."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        hidden_for_export: tuple[QGraphicsItem, ...] = (
            self._name,
            self._bounding_rect,
            *self._port_labels.values(),
        )
        previous_visibility = [(item, item.isVisible()) for item in hidden_for_export]

        try:
            for item in hidden_for_export:
                item.setVisible(False)

            export_rect = self._export_bounding_rect()
            margin = 1.0
            export_rect = export_rect.adjusted(-margin, -margin, margin, margin)

            generator = QSvgGenerator()
            generator.setFileName(str(path))
            generator.setSize(
                QSize(
                    max(1, ceil(export_rect.width())),
                    max(1, ceil(export_rect.height())),
                )
            )
            generator.setViewBox(
                QRectF(0, 0, export_rect.width(), export_rect.height())
            )
            generator.setTitle(self._data.figure)
            generator.setDescription(
                "Chemunited component figure exported without name or port labels."
            )

            root_to_export = QTransform()
            root_to_export.translate(-export_rect.left(), -export_rect.top())

            painter = QPainter()
            if not painter.begin(generator):
                raise OSError(f"Could not create SVG export at '{path}'.")
            try:
                painter.setRenderHint(QPainter.Antialiasing, True)
                painter.setRenderHint(QPainter.TextAntialiasing, True)
                painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
                self._paint_item_tree(painter, self, root_to_export)
            finally:
                painter.end()
        finally:
            for item, visible in previous_visibility:
                item.setVisible(visible)

    def _export_bounding_rect(self) -> QRectF:
        """Return a tight local bounding rect for visible exported child items."""
        scene_to_root = self._scene_to_root_transform()
        bounds: QRectF | None = None

        def visit(item: QGraphicsItem) -> None:
            nonlocal bounds
            if not item.isVisible():
                return
            if item is not self:
                item_to_root = item.sceneTransform() * scene_to_root
                item_rect = item_to_root.mapRect(item.boundingRect())
                bounds = item_rect if bounds is None else bounds.united(item_rect)
            for child in item.childItems():
                visit(child)

        visit(self)
        return bounds if bounds is not None else self.boundingRect()

    def _paint_item_tree(
        self,
        painter: QPainter,
        item: QGraphicsItem,
        root_to_export: QTransform,
    ) -> None:
        """Paint this item tree into the active painter."""
        if not item.isVisible():
            return

        option = QStyleOptionGraphicsItem()
        option.exposedRect = item.boundingRect()

        scene_to_root = self._scene_to_root_transform()
        item_to_export = item.sceneTransform() * scene_to_root * root_to_export

        painter.save()
        painter.setTransform(item_to_export)
        painter.setOpacity(item.effectiveOpacity())
        item.paint(painter, option, None)
        painter.restore()

        children = sorted(item.childItems(), key=lambda child: child.zValue())
        for child in children:
            self._paint_item_tree(painter, child, root_to_export)

    def _scene_to_root_transform(self) -> QTransform:
        scene_to_root, invertible = self.sceneTransform().inverted()
        return scene_to_root if invertible else QTransform()

    # ── Qt overrides ───────────────────────────────────────────────

    def hoverEnterEvent(self, event):
        self.highlight(True)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.highlight(False)
        super().hoverLeaveEvent(event)

    def itemChange(self, change, value):
        """Notify connected edges when position changes; toggle selection visual."""
        if change == QGraphicsItem.ItemPositionHasChanged:
            for point in self._points.values():
                point.connectionMove()
        elif change == QGraphicsItem.ItemSelectedHasChanged:
            selected = bool(value)
            self._bounding_rect.setPen(
                QPen(QColor("#1E88E5"), 2) if selected else QPen(Qt.black, 1)  # type: ignore
            )
            self.show_bounding_rect(selected)
        return super().itemChange(change, value)
