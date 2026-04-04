from functools import partial
from typing import TYPE_CHECKING, override

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import QGraphicsItem
from qfluentwidgets import Action, FluentIcon, RoundMenu

from chemunited.qt.elements.component.component_parts.connection_point import (
    ConnectionPoint,
)
from chemunited.qt.elements.component.graph_item import GraphComponent
from chemunited.qt.elements.connection.connection import (
    BaseConnectionItem,
    HydraulicConnectionItem,
    TemporaryConnectionItem,
)
from chemunited.qt.shared.enums import SetupStepMode
from chemunited.qt.shared.graph import GraphCore, SceneCore
from chemunited.qt.shared.icon import OrchestratorIcon

from .tree_add import TreeAddItem

if TYPE_CHECKING:
    from ..setup import SetupWindow


class DrawGraphicView(GraphCore):
    MODE = SetupStepMode.DESIGN

    connection_requested = pyqtSignal(ConnectionPoint, ConnectionPoint)

    def __init__(self, scene: SceneCore | None = None, parent=None):
        super().__init__(scene, parent)
        self.setObjectName("drawGraph")
        self.setFocusPolicy(Qt.StrongFocus)
        if parent is not None:
            self.parent_ref: SetupWindow = parent

        self._connecting: bool = False
        self._origin_port: ConnectionPoint | None = None
        self._temp_connection: TemporaryConnectionItem | None = None
        self._candidate: ConnectionPoint | None = None

    def _port_at(self, scene_pos) -> ConnectionPoint | None:
        for item in self.scene().items(scene_pos):
            if isinstance(item, ConnectionPoint):
                return item
        return None

    def _highlight_candidate(self, port: ConnectionPoint | None) -> None:
        if self._candidate is not None:
            self._candidate.setEvidence(False)
        self._candidate = port
        if port is not None:
            port.setEvidence(True)

    def _cleanup(self) -> None:
        if self._temp_connection is not None:
            self.scene().removeItem(self._temp_connection)
        self._highlight_candidate(None)
        self._connecting = False
        self._origin_port = None
        self._temp_connection = None
        self._candidate = None

    def _resolve_context_target(
        self, item: QGraphicsItem | None
    ) -> GraphComponent | BaseConnectionItem | None:
        current = item
        while current is not None:
            if isinstance(current, (GraphComponent, BaseConnectionItem)):
                return current
            current = current.parentItem()
        return None

    def _snapshot_delete_names(
        self, target: GraphComponent | BaseConnectionItem
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        scene_items = (
            set(self.scene().selectedItems()) if target.isSelected() else {target}
        )

        component_names = tuple(
            name
            for name, comp in self.parent_ref.orchestrator.components.items()
            if comp.graph in scene_items
        )
        connection_names = tuple(
            name
            for name, conn in self.parent_ref.orchestrator.connections.items()
            if conn in scene_items
            or conn.inf.origin in component_names
            or conn.inf.destination in component_names
        )
        return component_names, connection_names

    def _delete_snapshot(
        self,
        component_names: tuple[str, ...],
        connection_names: tuple[str, ...],
    ) -> None:
        orchestrator = self.parent_ref.orchestrator
        for name in connection_names:
            if name in orchestrator.connections:
                orchestrator.remove_connection(name)
        for name in component_names:
            if name in orchestrator.components:
                orchestrator.remove_component(name)
        self.scene().clearSelection()

    @override
    def mousePressEvent(self, event):
        self.setFocus()
        scene_pos = self.mapToScene(event.pos())
        port = self._port_at(scene_pos)
        if port is not None:
            self._connecting = True
            self._origin_port = port
            self._temp_connection = TemporaryConnectionItem(port)
            self.scene().addItem(self._temp_connection)
            event.accept()
            return
        super().mousePressEvent(event)

    @override
    def mouseDoubleClickEvent(self, event):
        target = self._resolve_context_target(self.itemAt(event.pos()))
        if target is None:
            super().mouseDoubleClickEvent(event)
            return

        if isinstance(target, GraphComponent):
            self.parent_ref.orchestrator.show_properties(target.inf.name)
        event.accept()

    @override
    def mouseMoveEvent(self, event):
        scene_pos = self.mapToScene(event.pos())
        self._highlight_candidate(self._port_at(scene_pos))
        if self._connecting:
            self._temp_connection.update_path(scene_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    @override
    def mouseReleaseEvent(self, event):
        if self._connecting:
            scene_pos = self.mapToScene(event.pos())
            port = self._port_at(scene_pos)
            if port is not None and port is not self._origin_port:
                self.connection_requested.emit(self._origin_port, port)
            self._cleanup()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    @override
    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(TreeAddItem.MIME):
            event.acceptProposedAction()
        else:
            event.ignore()

    @override
    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(TreeAddItem.MIME):
            event.acceptProposedAction()
        else:
            event.ignore()

    @override
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete and not self._connecting:
            if self.parent_ref is not None:
                for item in self.scene().selectedItems():
                    if isinstance(item, GraphComponent):
                        QTimer.singleShot(
                            0,
                            lambda name=item.inf.name: self.parent_ref.orchestrator.remove_component(
                                name
                            ),
                        )
                    elif isinstance(item, BaseConnectionItem):
                        QTimer.singleShot(
                            0,
                            lambda name=item.inf.name: self.parent_ref.orchestrator.remove_connection(
                                name
                            ),
                        )
            event.accept()
            return
        super().keyPressEvent(event)

    @override
    def contextMenuEvent(self, event):
        if self.parent_ref is None:
            super().contextMenuEvent(event)
            return

        target = self._resolve_context_target(self.itemAt(event.pos()))
        if target is None:
            super().contextMenuEvent(event)
            return

        component_names, connection_names = self._snapshot_delete_names(target)

        menu = RoundMenu(parent=self)

        if isinstance(target, BaseConnectionItem):
            shape_action = Action(menu)
            shape_action.setText(
                "Switch to Curved" if target._straight else "Switch to Straight"
            )
            shape_action.setIcon(OrchestratorIcon.CONNECTION.icon())
            shape_action.triggered.connect(
                lambda checked=False, t=target: QTimer.singleShot(
                    0, lambda: t.setStraight(not t._straight)
                )
            )
            menu.addAction(shape_action)

            add_inflection_action = Action(menu)
            add_inflection_action.setText("Add Inflection Point")
            add_inflection_action.setIcon(OrchestratorIcon.MOVE.icon())
            add_inflection_action.triggered.connect(
                lambda checked=False, t=target: QTimer.singleShot(
                    0, lambda: t.addInflectionPoint()
                )
            )
            menu.addAction(add_inflection_action)

            remove_inflection_action = Action(menu)
            remove_inflection_action.setText("Remove Inflection Point")
            remove_inflection_action.setIcon(OrchestratorIcon.SCISSOR.icon())
            remove_inflection_action.setEnabled(bool(target._inflection_points))
            remove_inflection_action.triggered.connect(
                lambda checked=False, t=target: QTimer.singleShot(
                    0, lambda: t.removeInflectionPoint()
                )
            )
            menu.addAction(remove_inflection_action)

            if isinstance(target, HydraulicConnectionItem):
                menu.addSeparator()
                is_air = target._data.air_pressure_line
                air_action = Action(menu)
                air_action.setText(
                    "Switch to Liquid" if is_air else "Switch to Air Pressure"
                )
                air_action.setIcon(
                    OrchestratorIcon.WATER.icon()
                    if is_air
                    else OrchestratorIcon.PRESSURE_LINE.icon()
                )
                air_action.triggered.connect(
                    lambda checked=False, t=target: QTimer.singleShot(
                        0,
                        lambda: t.set_air_pressure_line(not t._data.air_pressure_line),
                    )
                )
                menu.addAction(air_action)

            menu.addSeparator()

        if isinstance(target, GraphComponent):
            properties_action = Action(menu)
            properties_action.setText("Properties")
            properties_action.setIcon(FluentIcon.EDIT.icon())
            properties_action.triggered.connect(
                partial(self.parent_ref.orchestrator.show_properties, target.inf.name)
            )
            menu.addAction(properties_action)
            menu.addSeparator()

        delete_action = Action(menu)
        delete_action.setText("Delete")
        delete_action.setIcon(OrchestratorIcon.TRASH.icon())
        delete_action.triggered.connect(
            lambda checked=False, comps=component_names, conns=connection_names: QTimer.singleShot(
                0, lambda: self._delete_snapshot(comps, conns)
            )
        )
        menu.addAction(delete_action)
        menu.exec_(event.globalPos())

        event.accept()

    @override
    def dropEvent(self, event):
        if not event.mimeData().hasFormat(TreeAddItem.MIME):
            event.ignore()
            return

        data = bytes(event.mimeData().data(TreeAddItem.MIME)).decode(
            "utf-8"
        )  # "group|component"
        if "|" not in data:
            event.ignore()
            return

        group, component = data.split("|", 1)

        scene_pos = self.mapToScene(event.pos())

        if self.parent_ref is not None:
            self.parent_ref.orchestrator.request_add_component(
                figure=component, position=(scene_pos.x(), scene_pos.y())
            )

        event.acceptProposedAction()
