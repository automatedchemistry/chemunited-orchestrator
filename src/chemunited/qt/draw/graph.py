from typing import TYPE_CHECKING, override

from PyQt5.QtCore import pyqtSignal

from chemunited.qt.draw.elements.component.component_parts.connection_point import (
    ConnectionPoint,
)
from chemunited.qt.draw.elements.component.graph_item import GraphComponent
from chemunited.qt.draw.elements.connection.connection import TemporaryConnectionItem
from chemunited.qt.shared.enums import SetupStepMode
from chemunited.qt.shared.graph import GraphCore, SceneCore

from .tree_add import TreeAddItem

if TYPE_CHECKING:
    from ..setup import SetupWindow


class DrawGraphicView(GraphCore):
    MODE = SetupStepMode.DESIGN

    connection_requested = pyqtSignal(ConnectionPoint, ConnectionPoint)

    def __init__(self, scene: SceneCore | None = None, parent=None):
        super().__init__(scene, parent)
        self.setObjectName("drawGraph")
        if parent is not None:
            self.parent_ref: SetupWindow = parent

        self._connecting: bool = False
        self._origin_port: ConnectionPoint | None = None
        self._temp_connection: TemporaryConnectionItem | None = None
        self._candidate: ConnectionPoint | None = None

    # ── connection helpers ────────────────────────────────────────

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

    def _component_at(self, scene_pos) -> str:
        for item in self.scene().items(scene_pos):
            if hasattr(item, "parent_ref") and isinstance(
                item.parent_ref, GraphComponent
            ):
                return item.parent_ref._data.name
        return ""

    # ── mouse overrides ───────────────────────────────────────────

    @override
    def mousePressEvent(self, event):
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
