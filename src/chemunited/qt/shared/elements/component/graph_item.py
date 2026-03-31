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

from chemunited_core.components import ComponentData
from chemunited_core.common.enums import ConnectionType as CoreConnectionType

from PyQt5.QtWidgets import (
    QGraphicsItemGroup,
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsDropShadowEffect,
)
from PyQt5.QtGui import QColor

from chemunited.shared.enums import SetupStepMode
from chemunited.shared.elements.access import get_svg_path
from .parts import (
    ConnectionPoint,
    FlowConnectionPoint,
    HeatConnectionPoint,
    ElectronicConnectionPoint,
    MoveConnectionPoint,
    TextElement,
    ConnectivityBadge,
    WarningDisplay,
    StatusOverlay,
    SvgLayer,
)
from .parts.scene_item import PATTERN_DIMENSION

# Maps chemunited_core ConnectionType values to their visual point classes.
# HYDRAULIC is the core counterpart of what the UI layer calls FLOW.
_POINT_FACTORY: dict[CoreConnectionType, type[ConnectionPoint]] = {
    CoreConnectionType.HYDRAULIC:  FlowConnectionPoint,
    CoreConnectionType.HEAT:       HeatConnectionPoint,
    CoreConnectionType.ELECTRONIC: ElectronicConnectionPoint,
    CoreConnectionType.MOVEMENT:   MoveConnectionPoint,
}

# Radius used for FlowConnectionPoints (Heat/Electronic/Move derive their own
# radius internally from PATTERN_DIMENSION).
_FLOW_RADIUS: int = PATTERN_DIMENSION // 10


def _make_shadow(blur: int = 12, color: str = "#1E88E5") -> QGraphicsDropShadowEffect:
    """Return a pre-configured drop-shadow effect."""
    fx = QGraphicsDropShadowEffect()
    fx.setBlurRadius(blur)
    fx.setColor(QColor(color))
    fx.setOffset(0, 0)
    return fx


class GraphComponent(QGraphicsItemGroup):
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
    """

    def __init__(self, data: ComponentData) -> None:
        super().__init__()

        self._data: ComponentData = data
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

        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)  # type: ignore
        self.setFlag(QGraphicsItem.ItemIsMovable, True)  # type: ignore

        self.build()
        self.post_layout()

    # ── construction ───────────────────────────────────────────────

    def build(self) -> None:
        """Assemble all child items from ComponentData.

        Called once from __init__. Subclasses may override to implement
        a custom layout — call super().build() or fully replace it.
        """
        # SVG figure, or fallback rect when no SVG asset is available.
        svg_path = get_svg_path(self._data.figure)
        if svg_path:
            self._svg = SvgLayer(svg_path, angle=self._data.angle)
        else:
            self._svg = QGraphicsRectItem(
                -PATTERN_DIMENSION / 2,
                -PATTERN_DIMENSION / 2,
                PATTERN_DIMENSION,
                PATTERN_DIMENSION,
            )
        self.addToGroup(self._svg)

        # Connection points — one per port.
        for port_num, port in self._data.ports_by_number.items():
            pos = (
                port.relative_position[0] * PATTERN_DIMENSION / 2,
                port.relative_position[1] * PATTERN_DIMENSION / 2,
            )
            cls = _POINT_FACTORY.get(port.category, FlowConnectionPoint)
            if cls is FlowConnectionPoint:
                point: ConnectionPoint = cls(
                    position=pos,
                    radius=_FLOW_RADIUS,
                    id_connection=str(port_num),
                )
            else:
                point = cls(position=pos, id_connection=str(port_num))
            self._points[port_num] = point
            self.addToGroup(point)

        # Port labels — positioned outward from the connection point.
        for port_num, port in self._data.ports_by_number.items():
            label_x = port.relative_position[0] * PATTERN_DIMENSION / 2 * 1.5
            label_y = port.relative_position[1] * PATTERN_DIMENSION / 2 * 1.5
            label = TextElement(str(port_num))
            label.setPos(label_x, label_y)
            self._port_labels[port_num] = label
            self.addToGroup(label)

        # Plain children — follow the group but don't affect its bounding rect.
        self._name = TextElement(self._data.name)
        self._name.setParentItem(self)

        if self._data.is_electronic:
            self._badge = ConnectivityBadge(dimension=PATTERN_DIMENSION // 3)
            self._badge.setParentItem(self)

        self._warning = WarningDisplay()
        self._warning.setParentItem(self)
        self._warning.setVisible(False)

        self._overlay = StatusOverlay(dimension=PATTERN_DIMENSION)
        self._overlay.setParentItem(self)
        self._overlay.setVisible(False)

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

    # ── public API ─────────────────────────────────────────────────

    def sync(self, data: ComponentData) -> None:
        """Reconcile visuals when ComponentData is updated externally.

        Only position and angle are expected to change after construction.
        Rebuilding the full item tree on every sync would be wasteful.
        """
        self._data = data
        self.setPos(data.position[0], data.position[1])
        if isinstance(self._svg, SvgLayer):
            self._svg.update_angle(data.angle)
        else:
            self._svg.setRotation(data.angle)
        # Rotation changes the bounding rect, so re-position plain children.
        self.post_layout()

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
            for pt in self._points.values():
                pt.setVisible(True)
            for lbl in self._port_labels.values():
                lbl.setVisible(True)
            if self._badge is not None:
                self._badge.setVisible(False)
            self._warning.setVisible(False)

        elif mode == SetupStepMode.PROTOCOLS:
            self.setFlag(QGraphicsItem.ItemIsMovable, True)  # type: ignore
            self._deletable = False
            for pt in self._points.values():
                pt.setVisible(True)
            for lbl in self._port_labels.values():
                lbl.setVisible(True)
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

    # ── Qt overrides ───────────────────────────────────────────────

    def itemChange(self, change, value):
        """Notify connected edges when position changes."""
        if change == QGraphicsItem.ItemPositionHasChanged:
            for point in self._points.values():
                point.connectionMove()
        return super().itemChange(change, value)


if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication, QGraphicsView, QGraphicsScene
    from chemunited_core.elements import ComponentData

    app = QApplication(sys.argv)
    scene = QGraphicsScene()

    data = ComponentData(
        name="TestPump",
        figure="SyringePump",
        position=(0.0, 0.0),
        angle=0,
    )

    component = GraphComponent(data)
    scene.addItem(component)

    view = QGraphicsView(scene)
    view.setRenderHint(view.Antialiasing)
    view.show()
    sys.exit(app.exec_())
