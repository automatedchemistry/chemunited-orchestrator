from __future__ import annotations

from functools import partial

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QPainter, QPen
from PyQt5.QtWidgets import QFrame, QGraphicsItem, QGraphicsView
from qfluentwidgets import Action, RoundMenu, isDarkTheme

from chemunited.shared.enums import SetupStepMode, WindowCategory
from chemunited.shared.enums.protocols_enum import ProtocolBlock
from chemunited.shared.graph import GraphCore, SceneCore
from chemunited.shared.icon import OrchestratorIcon
from chemunited.shared.workflows.controller import WorkflowController
from chemunited.shared.workflows.exceptions import WorkflowRuleViolation
from chemunited.shared.workflows.process_workflow import BlockData, ConnectionData
from chemunited.shared.workflows.workflow_rules import resolve_render_start_role

from .elements.access_point import WorkflowAccessPoints
from .elements.work_connection import WorkflowConnection
from .elements.work_node import WorkflowNode


class WorkflowGraph(GraphCore):
    """
    A graph view for workflows.
    """

    WINDOW_CONTAINER: WindowCategory = WindowCategory.SETUP
    MODE: SetupStepMode = SetupStepMode.DESIGN

    def __init__(
        self,
        window_container: WindowCategory,
        controller: WorkflowController | None = None,
        parent=None,
    ):
        super().__init__(parent=parent)
        self.parent_ref = parent
        self.window_container = window_container
        self.controller = (
            controller if controller is not None else WorkflowController(parent=self)
        )
        self.scene_attribute = SceneCore(self)
        self.setScene(self.scene_attribute)
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setFrameShape(QFrame.NoFrame)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)

        self._nodes: dict[str, WorkflowNode] = {}
        self._connections: dict[tuple[str, str], WorkflowConnection] = {}
        self._selected_port: WorkflowAccessPoints | None = None

        self._bind_controller()
        self.build_from_model()

    @property
    def model(self):
        return self.controller.model

    def _bind_controller(self):
        self.controller.model_reset.connect(self.build_from_model)
        self.controller.block_added.connect(self._on_block_added)
        self.controller.block_updated.connect(self._on_block_updated)
        self.controller.block_removed.connect(self._on_block_removed)
        self.controller.connection_added.connect(self._on_connection_added)
        self.controller.connection_updated.connect(self._on_connection_updated)
        self.controller.connection_removed.connect(self._on_connection_removed)

    def drawBackground(self, painter: QPainter | None, rect: QRectF) -> None:
        if painter is None:
            return
        background = QColor(39, 39, 39) if isDarkTheme() else QColor(249, 249, 249)
        grid = QColor(255, 255, 255, 18) if isDarkTheme() else QColor(0, 0, 0, 16)
        painter.fillRect(rect, background)
        painter.setPen(QPen(grid, 1))

        step = 28
        left = int(rect.left()) - (int(rect.left()) % step)
        top = int(rect.top()) - (int(rect.top()) % step)

        x = left
        while x < rect.right():
            painter.drawLine(int(x), int(rect.top()), int(x), int(rect.bottom()))
            x += step

        y = top
        while y < rect.bottom():
            painter.drawLine(int(rect.left()), int(y), int(rect.right()), int(y))
            y += step

    def wheelEvent(self, event):
        zoom_factor = 1.12 if event.angleDelta().y() > 0 else 1 / 1.12
        self.scale(zoom_factor, zoom_factor)

    def doubleClickEvent(self, event):
        item = self.itemAt(event.pos())
        if isinstance(item, WorkflowNode):
            self._handle_node_double_click(item)
            event.accept()
            return
        super().doubleClickEvent(event)

    def _handle_node_double_click(self, node: WorkflowNode):
        if self.window_container != WindowCategory.SETUP:
            return

    def mousePressEvent(self, event):
        self.setFocus()
        if event.button() == Qt.MouseButton.LeftButton:
            item = self.itemAt(event.pos())
            access_point = self._resolve_access_point_target(item)
            if access_point is not None:
                self._handle_access_point_click(access_point)
                event.accept()
                return
            if self._selected_port:
                self._clear_selected_port()

        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if self.window_container != WindowCategory.SETUP:
            return
        if event.key() == Qt.Key.Key_Delete:
            if self._delete_selected_items():
                event.accept()
                return
            if self._selected_port:
                self._clear_selected_port()
                event.accept()
                return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        if self.window_container != WindowCategory.SETUP:
            super().contextMenuEvent(event)
            return
        item = self.itemAt(event.pos())
        context_target = self._resolve_context_target(item)

        if isinstance(context_target, WorkflowNode):
            self._build_node_menu(context_target).exec(event.globalPos())
            event.accept()
            return

        if isinstance(context_target, WorkflowConnection):
            self._build_connection_menu(context_target).exec(event.globalPos())
            event.accept()
            return

        if not item:
            scene_pos = self.mapToScene(event.pos())
            self._build_add_menu(scene_pos).exec(event.globalPos())
            event.accept()
            return
        super().contextMenuEvent(event)

    def _build_add_menu(self, scene_pos: QPointF) -> RoundMenu:
        menu = RoundMenu(parent=self)

        actions = (
            ("Add Script", ProtocolBlock.SCRIPT, OrchestratorIcon.PYTHON.icon()),
            ("Add Loop", ProtocolBlock.LOOP, OrchestratorIcon.LOOP.icon()),
            ("Add Conditional", ProtocolBlock.IF, OrchestratorIcon.IF.icon()),
        )
        for text, block_tag, icon in actions:
            action = Action(self)
            action.setText(text)
            action.setIcon(icon)
            action.triggered.connect(partial(self.add_block, block_tag, scene_pos))
            menu.addAction(action)

        return menu

    def _build_node_menu(self, node: WorkflowNode) -> RoundMenu:
        menu = RoundMenu(parent=self)

        delete_action = Action(self)
        delete_action.setText("Delete block")
        delete_action.setIcon(OrchestratorIcon.TRASH.icon())
        delete_action.setEnabled(not node.is_protected)
        delete_action.triggered.connect(partial(self.remove_node, node.node_name))
        menu.addAction(delete_action)

        return menu

    def _build_connection_menu(self, connection: WorkflowConnection) -> RoundMenu:
        menu = RoundMenu(parent=self)

        add_second_action = Action(self)
        add_second_action.setText(
            "Add inflection point"
            if not connection.inflection_points
            else "Add second inflection point"
        )
        add_second_action.setEnabled(len(connection.inflection_points) < 2)
        add_second_action.triggered.connect(connection.add_inflection_point)
        menu.addAction(add_second_action)

        remove_second_action = Action(self)
        remove_second_action.setText("Remove second inflection point")
        remove_second_action.setEnabled(len(connection.inflection_points) == 2)
        remove_second_action.triggered.connect(connection.remove_last_inflection_point)
        menu.addAction(remove_second_action)

        reset_action = Action(self)
        reset_action.setText("Reset inflection points")
        reset_action.setEnabled(bool(connection.inflection_points))
        reset_action.triggered.connect(connection.clear_inflection_points)
        menu.addAction(reset_action)

        delete_action = Action(self)
        delete_action.setText("Delete connection")
        delete_action.setIcon(OrchestratorIcon.TRASH.icon())
        delete_action.triggered.connect(
            partial(self.remove_connection, connection.start_node, connection.end_node)
        )
        menu.addAction(delete_action)

        return menu

    def _resolve_context_target(
        self, item: QGraphicsItem | None
    ) -> WorkflowNode | WorkflowConnection | None:
        current_item = item
        while current_item is not None:
            if isinstance(current_item, (WorkflowNode, WorkflowConnection)):
                return current_item
            current_item = current_item.parentItem()
        return None

    def _resolve_access_point_target(
        self, item: QGraphicsItem | None
    ) -> WorkflowAccessPoints | None:
        current_item = item
        while current_item is not None:
            if isinstance(current_item, WorkflowAccessPoints):
                return current_item
            current_item = current_item.parentItem()
        return None

    def build_from_model(self):
        self._clear_scene_objects()

        for _, block in self.controller.iter_blocks():
            self._add_node_from_block(block)

        for start, end, connection in self.controller.iter_connections():
            self._add_connection_from_model(start, end, connection)

        for node_name in self._nodes:
            self._sync_input_ports(node_name)

    def _clear_scene_objects(self):
        self.scene_attribute.clear()
        self._nodes = {}
        self._connections = {}
        self._selected_port = None

    def _display_text(self, name: str, block_tag: ProtocolBlock) -> tuple[str, str]:
        labels = {
            ProtocolBlock.START: ("Start", "Entry"),
            ProtocolBlock.END: ("End", "Exit"),
            ProtocolBlock.SCRIPT: (name, "Module"),
            ProtocolBlock.LOOP: (name, "Repeat"),
            ProtocolBlock.IF: (name, "Branch"),
        }
        return labels[block_tag]

    def _add_node_from_block(self, block: BlockData) -> WorkflowNode:
        title, subtitle = self._display_text(block.name, block.block_tag)
        node = WorkflowNode(
            node_name=block.name,
            block_tag=block.block_tag,
            title=title,
            subtitle=subtitle,
            ports_numbers=block.ports_numbers,
            protected=block.protected,
            on_position_changed=self._on_node_moved,
        )
        node.sync_position(block.pos)
        self.scene_attribute.addItem(node)
        self._nodes[block.name] = node
        return node

    def _resolve_start_port(
        self,
        node: WorkflowNode | None,
        connection: ConnectionData,
    ) -> WorkflowAccessPoints | None:
        if node is None:
            return None

        start_role = resolve_render_start_role(
            node.block_tag,
            start_role=connection.start_role,
            loopback=connection.loopback,
            trigger_on=connection.trigger_on,
            condition=connection.condition,
        )
        if start_role == "top":
            return node.top_ports
        if start_role == "bottom":
            return node.bottom_ports
        return node.output_ports

    def _add_connection_from_model(
        self, start: str, end: str, connection_data: ConnectionData
    ) -> WorkflowConnection | None:
        start_node = self._nodes.get(start)
        end_node = self._nodes.get(end)
        if start_node is None or end_node is None or end_node.input_ports is None:
            return None

        start_port = self._resolve_start_port(start_node, connection_data)
        if start_port is None:
            return None

        connection = WorkflowConnection(
            start_port,
            end_node.input_ports,
            inflection_points=connection_data.inflection_points,
            edge_data=connection_data.to_attrs(),
            on_geometry_changed=self._on_connection_geometry_changed,
        )
        self._connections[(start, end)] = connection
        self.scene_attribute.addItem(connection)
        connection.updateConnection()
        return connection

    def _delete_selected_items(self) -> bool:
        selected_nodes: set[str] = set()
        selected_connections: set[tuple[str, str]] = set()

        for item in self.scene_attribute.selectedItems():
            target = self._resolve_context_target(item)
            if isinstance(target, WorkflowNode):
                selected_nodes.add(target.node_name)
            elif isinstance(target, WorkflowConnection):
                selected_connections.add((target.start_node, target.end_node))

        if not selected_nodes and not selected_connections:
            return False

        deleted_any = False
        for start_node, end_node in selected_connections:
            if self.controller.has_connection(start_node, end_node):
                self.controller.remove_connection(start_node, end_node)
                deleted_any = True

        for node_name in selected_nodes:
            try:
                self.controller.remove_block(node_name)
            except WorkflowRuleViolation:
                continue
            deleted_any = True

        return deleted_any

    def add_block(
        self,
        block_tag: ProtocolBlock,
        scene_pos: QPointF,
        ports_numbers: int = 1,
    ):
        self.controller.add_block(
            block_tag=block_tag,
            pos=(scene_pos.x(), scene_pos.y()),
            ports_numbers=ports_numbers,
        )

    def _handle_access_point_click(self, port: WorkflowAccessPoints):
        if self.window_container != WindowCategory.SETUP:
            return
        if self._selected_port is None:
            if port.can_start_connection:
                self._set_selected_port(port)
            return

        if port is self._selected_port:
            self._clear_selected_port()
            return

        if port.can_start_connection:
            self._set_selected_port(port)
            return

        if not port.can_end_connection:
            self._clear_selected_port()
            return

        start_node = self._selected_port.node
        end_node = port.node
        if start_node is None or end_node is None:
            self._clear_selected_port()
            return

        try:
            self.controller.connect_nodes(
                start_name=start_node.node_name,
                end_name=end_node.node_name,
                start_role=self._selected_port.role,
            )
        except WorkflowRuleViolation:
            pass
        finally:
            self._clear_selected_port()

    def _set_selected_port(self, port: WorkflowAccessPoints):
        if self.window_container != WindowCategory.SETUP:
            return
        if self._selected_port:
            self._selected_port.set_selected(False)
        self._selected_port = port
        self._selected_port.set_selected(True)

    def _clear_selected_port(self):
        if self._selected_port:
            self._selected_port.set_selected(False)
        self._selected_port = None

    def _sync_input_ports(self, node_name: str):
        node = self._nodes.get(node_name)
        if node is None:
            return
        node.set_input_port_count(self.controller.incoming_port_count(node_name))

    def _on_node_moved(self, node: WorkflowNode):
        self.update_connections()
        self.controller.move_block(
            node.node_name,
            (node.pos().x(), node.pos().y()),
        )

    def _on_connection_geometry_changed(self, connection: WorkflowConnection):
        self.controller.update_connection_geometry(
            connection.start_node,
            connection.end_node,
            [
                (point.x(), point.y())
                for point in connection.inflection_points
            ],
        )

    def _on_block_added(self, name: str):
        block = self.controller.get_block(name)
        if block is None or name in self._nodes:
            return
        self._add_node_from_block(block)
        self._sync_input_ports(name)

    def _on_block_updated(self, name: str):
        block = self.controller.get_block(name)
        if block is None:
            return

        node = self._nodes.get(name)
        if node is None:
            self._add_node_from_block(block)
            self._sync_input_ports(name)
            self.update_connections()
            return

        node.protected = block.protected
        if (node.pos().x(), node.pos().y()) != block.pos:
            node.sync_position(block.pos)
        self._sync_input_ports(name)
        self.update_connections()

    def _on_block_removed(self, name: str):
        node = self._nodes.pop(name, None)
        if node is None:
            return

        if self._selected_port and self._selected_port.node is node:
            self._clear_selected_port()
        self.scene_attribute.removeItem(node)

    def _on_connection_added(self, start: str, end: str):
        if (start, end) in self._connections:
            return
        connection = self.controller.get_connection(start, end)
        if connection is None:
            return
        self._add_connection_from_model(start, end, connection)
        self._sync_input_ports(end)

    def _on_connection_updated(self, start: str, end: str):
        connection_data = self.controller.get_connection(start, end)
        if connection_data is None:
            return

        connection = self._connections.get((start, end))
        if connection is None:
            self._add_connection_from_model(start, end, connection_data)
        else:
            connection.sync_from_model(connection_data.to_attrs())
        self._sync_input_ports(end)
        self.update_connections()

    def _on_connection_removed(self, start: str, end: str):
        connection = self._connections.pop((start, end), None)
        if connection is None:
            return
        self.scene_attribute.removeItem(connection)
        self._sync_input_ports(end)

    def update_connections(self):
        for connection in self._connections.values():
            connection.updateConnection()

    def remove_connection(self, start_node: str, end_node: str):
        self.controller.remove_connection(start_node, end_node)

    def remove_node(self, node_name: str):
        try:
            self.controller.remove_block(node_name)
        except WorkflowRuleViolation:
            return

    def start_progress(self, node_name: str):
        node = self._nodes.get(node_name)
        if node is None:
            return
        node.start_progress()

    def stop_progress(self, node_name: str):
        node = self._nodes.get(node_name)
        if node is None:
            return
        node.stop_progress()

    def clear_progress(self):
        for node in self._nodes.values():
            node.stop_progress()

    def clear_workflow(self):
        self._clear_selected_port()
        self.controller.clear_workflow()
