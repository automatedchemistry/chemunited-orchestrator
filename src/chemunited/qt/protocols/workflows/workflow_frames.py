from __future__ import annotations

import ast
import textwrap
from functools import partial
from pathlib import Path
from typing import override

from chemunited_workflow.enums import NodeState
from loguru import logger
from PyQt5 import sip
from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QPainter, QPen
from PyQt5.QtWidgets import QFrame, QGraphicsItem, QGraphicsView
from qfluentwidgets import Action, RoundMenu, isDarkTheme

from chemunited_core.protocols import CommandSignature
from chemunited.qt.protocols.workflows.naming import (
    process_class_name,
    process_config_class_name,
)
from chemunited.qt.shared.editor.parameters.main import MainParametersEditor
from chemunited.qt.shared.editor.protocols.command import CommandEditorDialog
from chemunited.qt.shared.editor.protocols.command_list import CommandList
from chemunited.qt.shared.enums import SetupStepMode, WindowCategory
from chemunited.qt.shared.enums.protocols_enum import ProtocolBlock
from chemunited.qt.shared.graph import GraphCore, SceneCore
from chemunited.qt.shared.icon import OrchestratorIcon

from .controller import WorkflowController
from .editor import ProcessScriptEditorWindow
from .elements.access_point import WorkflowAccessPoints
from .elements.work_connection import WorkflowConnection
from .elements.work_node import WorkflowNode
from .exceptions import WorkflowRuleViolation
from .process_workflow import BlockData, ConnectionData
from .workflow_rules import resolve_render_start_role


def _add_method_stub(source: str, method_name: str, class_name: str) -> str:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source

    class_node = next(
        (
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.ClassDef) and n.name == class_name
        ),
        None,
    )
    if class_node is None:
        return source

    existing = {
        n.name
        for n in class_node.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    if method_name in existing:
        return source

    lines = source.splitlines(keepends=True)
    indent = "    "
    for node in class_node.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            raw = lines[node.lineno - 1]
            indent = " " * (len(raw) - len(raw.lstrip()))
            break

    newline = "\r\n" if "\r\n" in source else "\n"
    stub = (
        f"{newline}{indent}def {method_name}(self, ctx: NodeExecutionContext) -> bool:"
        f"{newline}{indent}    return True{newline}"
    )
    insert_at = class_node.end_lineno or len(lines)
    lines.insert(insert_at, stub)
    return "".join(lines)


def _add_content_to_method(
    source: str, method_name: str, class_name: str, content: str
) -> str:
    if not content.strip():
        return source

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source

    class_node = next(
        (
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.ClassDef) and n.name == class_name
        ),
        None,
    )
    if class_node is None:
        return source

    method_node = next(
        (
            n
            for n in class_node.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == method_name
        ),
        None,
    )
    if method_node is None or not method_node.body:
        return source

    lines = source.splitlines(keepends=True)
    newline = "\r\n" if "\r\n" in source else "\n"
    body_indent = " " * method_node.body[0].col_offset
    normalized = textwrap.dedent(content).strip("\r\n")
    formatted = newline.join(
        f"{body_indent}{line}" if line else "" for line in normalized.splitlines()
    )
    insert_line = method_node.end_lineno or len(lines)
    if isinstance(method_node.body[-1], ast.Return):
        insert_line = method_node.body[-1].lineno - 1
    lines.insert(insert_line, f"{formatted}{newline}")
    return "".join(lines)


def _remove_method(source: str, method_name: str, class_name: str) -> str:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source

    class_node = next(
        (
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.ClassDef) and n.name == class_name
        ),
        None,
    )
    if class_node is None:
        return source

    method_node = next(
        (
            n
            for n in class_node.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == method_name
        ),
        None,
    )
    if method_node is None:
        return source

    lines = source.splitlines(keepends=True)
    start = (
        method_node.decorator_list[0].lineno
        if method_node.decorator_list
        else method_node.lineno
    ) - 1
    end = method_node.end_lineno

    while start > 0 and not lines[start - 1].strip():
        start -= 1

    del lines[start:end]
    return "".join(lines)


def _extract_method_first_expr(
    source: str, method_name: str, class_name: str
) -> str | None:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    class_node = next(
        (
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.ClassDef) and n.name == class_name
        ),
        None,
    )
    if class_node is None:
        return None
    method_node = next(
        (
            n
            for n in class_node.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == method_name
        ),
        None,
    )
    if method_node is None:
        return None
    for stmt in method_node.body:
        if isinstance(stmt, ast.Pass):
            continue
        seg = ast.get_source_segment(source, stmt)
        if seg:
            return seg.strip()
    return None


def _replace_method_body(
    source: str, method_name: str, class_name: str, new_content: str
) -> str:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source
    class_node = next(
        (
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.ClassDef) and n.name == class_name
        ),
        None,
    )
    if class_node is None:
        return source
    method_node = next(
        (
            n
            for n in class_node.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == method_name
        ),
        None,
    )
    if method_node is None or not method_node.body:
        return source
    lines = source.splitlines(keepends=True)
    newline = "\r\n" if "\r\n" in source else "\n"
    body_indent = " " * method_node.body[0].col_offset
    first_body = method_node.body[0].lineno - 1
    last_body = method_node.end_lineno
    replacement = f"{body_indent}{new_content.strip()}{newline}"
    lines[first_body:last_body] = [replacement]
    return "".join(lines)


def _parse_command_call(
    source: str, method_name: str, class_name: str
) -> tuple[str, str, dict[str, object]] | None:
    from chemunited_core.utils.internal_quantity import ChemUnitQuantity

    line = _extract_method_first_expr(source, method_name, class_name)
    if not line:
        return None

    try:
        expr = ast.parse(line, mode="eval").body
    except SyntaxError:
        return None
    if not isinstance(expr, ast.Call):
        return None
    func = expr.func
    if not isinstance(func, ast.Attribute):
        return None
    subscript = func.value
    if not (
        isinstance(subscript, ast.Subscript)
        and isinstance(subscript.slice, ast.Constant)
    ):
        return None
    component_name: str = subscript.slice.value
    if not expr.args or not isinstance(expr.args[0], ast.Constant):
        return None
    command_name: str = expr.args[0].value

    eval_ns = {"ChemUnitQuantity": ChemUnitQuantity}
    kwargs: dict[str, object] = {}
    for kw in expr.keywords:
        if kw.arg is None:
            continue
        try:
            kwargs[kw.arg] = ast.literal_eval(kw.value)
        except (ValueError, TypeError):
            try:
                kwargs[kw.arg] = eval(ast.unparse(kw.value), eval_ns)
            except Exception:
                pass

    return component_name, command_name, kwargs


def _build_command_model(
    source: str,
    method_name: str,
    class_name: str,
    sig_cls: type[CommandSignature] | None = None,
) -> "CommandSignature | None":

    parsed = _parse_command_call(source, method_name, class_name)
    if parsed is None:
        return None
    component_name, command_name, kwargs = parsed

    def _find_sig_class(cmd: str, base=CommandSignature):
        matches: list[type[CommandSignature]] = []
        for sub in base.__subclasses__():
            info = sub.model_fields.get("command")
            if info and info.default == cmd:
                matches.append(sub)
            matches.extend(_find_sig_class(cmd, sub))
        return matches

    if sig_cls is None:
        matches = _find_sig_class(command_name)
        if matches:
            # Prefer the most specific subclass when multiple commands share a name.
            sig_cls = max(matches, key=lambda cls: len(cls.mro()))
    if sig_cls is None:
        return None

    try:
        return sig_cls.model_validate({"component": component_name, **kwargs})
    except Exception:
        logger.warning(
            f"Could not instantiate {sig_cls.__name__} for command {command_name!r}"
        )
        return None


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

        self._script_editor: ProcessScriptEditorWindow | None = None
        self._parameters_editor: MainParametersEditor | None = None
        self._parameters_editor_target: tuple[Path, str] | None = None

        self._bind_controller()
        self.build_from_model()

    @override
    def closeEvent(self, event):
        self._close_auxiliary_windows()
        super().closeEvent(event)

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

    @override
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

    @override
    def wheelEvent(self, event):
        zoom_factor = 1.12 if event.angleDelta().y() > 0 else 1 / 1.12
        self.scale(zoom_factor, zoom_factor)

    @override
    def mouseDoubleClickEvent(self, event):
        item = self.itemAt(event.pos())
        context_target = self._resolve_context_target(item)
        if isinstance(context_target, WorkflowNode):
            self._handle_node_double_click(context_target)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def _handle_node_double_click(self, node: WorkflowNode):
        if self.window_container != WindowCategory.SETUP:
            return

        data = self.controller.get_block(node.node_name)
        if data is None:
            return

        tag = data.block_tag
        if tag in {ProtocolBlock.START, ProtocolBlock.END}:
            return

        script_path = self._resolve_script_path(data)
        if not self._is_valid_script_file(script_path):
            return
        assert script_path is not None

        data.file_path = script_path
        if not data.file:
            data.file = script_path.name

        if tag == ProtocolBlock.COMMAND:
            class_name = process_class_name(data.process)
            source = script_path.read_text(encoding="utf-8")
            parsed_command = _parse_command_call(source, data.method, class_name)
            if parsed_command is None:
                logger.warning(f"Could not parse command block {data.method!r}")
                return
            component_name, command_name, _kwargs = parsed_command
            command = _build_command_model(
                source,
                data.method,
                class_name,
                sig_cls=self._resolve_command_signature_class(
                    component_name,
                    command_name,
                ),
            )
            if command is None:
                logger.warning(
                    f"Could not reconstruct command for block {data.method!r}"
                )
                return
            editor = CommandEditorDialog(
                file_path=script_path,
                function_name=data.method or "",
                command_model=command,
                parent=self,
            )
            editor.saved.connect(
                lambda sig: self._update_command_script(data.method, sig)
            )
            editor.convert_to_script.connect(
                lambda _src: self._convert_command_to_script(data)
            )
            editor.exec_()
            return

        class_name = process_class_name(data.process)
        if (
            self._script_editor is None
            or self._script_editor.editor.path != script_path
        ):
            self._dispose_auxiliary_window("_script_editor")
            self._script_editor = ProcessScriptEditorWindow(
                path=script_path,
                class_name=class_name,
                main_parameters_path=script_path.parent / "main_parameters.py",
                parent=self,
            )

        if data.method:
            self._script_editor.focus_method(data.method)
        self._script_editor.show()
        self._script_editor.raise_()
        self._script_editor.activateWindow()

    def _close_auxiliary_windows(self) -> None:
        self._dispose_auxiliary_window("_script_editor")
        self._dispose_auxiliary_window("_parameters_editor")
        self._parameters_editor_target = None

    def _dispose_auxiliary_window(self, attr_name: str) -> None:
        window = getattr(self, attr_name, None)
        if window is None:
            return

        setattr(self, attr_name, None)
        try:
            if sip.isdeleted(window):
                return
            window.close()
            window.deleteLater()
        except RuntimeError:
            return

    def _resolve_command_signature_class(
        self,
        component_name: str,
        command_name: str,
    ) -> type[CommandSignature] | None:
        orchestrator = getattr(self.parent_ref, "orchestrator", None)
        components = getattr(orchestrator, "components", None)
        if components is None:
            return None

        manager = components.get(component_name)
        if manager is None:
            return None

        protocol = getattr(manager, "protocols", None)
        commands = getattr(protocol, "commands", None)
        if not isinstance(commands, dict):
            return None

        command_class = commands.get(command_name)
        if isinstance(command_class, type) and issubclass(
            command_class, CommandSignature
        ):
            return command_class
        return None

    def _resolve_script_path(self, block: BlockData) -> Path | None:
        if block.file_path is not None:
            return Path(block.file_path)

        if block.file:
            file_path = Path(block.file)
            if file_path.is_file():
                return file_path

        orchestrator = getattr(self.parent_ref, "orchestrator", None)
        working_dir = getattr(orchestrator, "working_dir", None)
        process_name = block.process or self.model.process
        if working_dir is None or not process_name:
            return None
        return Path(working_dir) / "protocols" / f"{process_name}.py"

    @staticmethod
    def _is_valid_script_file(path: Path | None) -> bool:
        if path is None or not path.is_file():
            return False

        try:
            source = path.read_text(encoding="utf-8")
            ast.parse(source)
        except (OSError, UnicodeError, SyntaxError):
            return False

        return True

    @override
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

    @override
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

    @override
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

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(CommandList.MIME):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(CommandList.MIME):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        """
        Add a command block from the command list.
        data format: "self.platform['component'].put('command', ...)"
        """
        if not event.mimeData().hasFormat(CommandList.MIME):
            event.ignore()
            return

        line_script = bytes(event.mimeData().data(CommandList.MIME)).decode("utf-8")
        scene_pos = self.mapToScene(event.pos())
        block = self.controller.add_block(
            block_tag=ProtocolBlock.COMMAND,
            pos=(scene_pos.x(), scene_pos.y()),
        )
        # stub already written by sync_script via _on_block_added; inject the command line
        self._inject_to_script(block.node_id, line_script)
        event.acceptProposedAction()

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
        menu.addSeparator()
        open_process_parameters_action = Action(self)
        open_process_parameters_action.setText("Access Process Parameters")
        open_process_parameters_action.setIcon(OrchestratorIcon.VARIABLE.icon())
        open_process_parameters_action.triggered.connect(self.access_process_parameters)
        menu.addAction(open_process_parameters_action)

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
            ProtocolBlock.COMMAND: (name, "Command"),
        }
        return labels[block_tag]

    def _add_node_from_block(self, block: BlockData) -> WorkflowNode:
        title, subtitle = self._display_text(block.node_id, block.block_tag)
        node = WorkflowNode(
            node_name=block.node_id,
            block_tag=block.block_tag,
            title=title,
            subtitle=subtitle,
            ports_numbers=block.ports_numbers,
            protected=block.protected,
            on_position_changed=self._on_node_moved,
        )
        node.sync_position(block.position)
        self.scene_attribute.addItem(node)
        self._nodes[block.node_id] = node
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
            [(point.x(), point.y()) for point in connection.inflection_points],
        )

    def _on_block_added(self, name: str):
        block = self.controller.get_block(name)
        if block is None or name in self._nodes:
            return
        self._add_node_from_block(block)
        self._sync_input_ports(name)
        if block.method and not block.protected:
            self.sync_script(block.method)

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
        if (node.pos().x(), node.pos().y()) != block.position:
            node.sync_position(block.position)
        self._sync_input_ports(name)
        self.update_connections()

    def _on_block_removed(self, name: str):
        node = self._nodes.pop(name, None)
        if node is None:
            return

        if self._selected_port and self._selected_port.node is node:
            self._clear_selected_port()
        if node.block_tag not in {ProtocolBlock.START, ProtocolBlock.END}:
            self.sync_script(name, removed=True)
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

    def set_node_status(self, node_name: str, status) -> None:
        node = self._nodes.get(node_name)
        if node is None:
            return
        node.set_status(status)

    def clear_progress(self):
        for node in self._nodes.values():
            node.set_status(NodeState.NOT_VISITED)

    def finalize_running_nodes(self, state: NodeState) -> None:
        for node in self._nodes.values():
            if node.progress_bar is not None and node.progress_bar.is_running():
                node.set_status(state)

    def clear_workflow(self):
        self._clear_selected_port()
        self.controller.clear_workflow()

    def sync_script(self, method_name: str, removed: bool = False) -> bool:
        orchestrator = getattr(self.parent_ref, "orchestrator", None)
        working_dir = getattr(orchestrator, "working_dir", None)
        process_name = self.model.process
        if not working_dir or not process_name:
            return False

        script_path = Path(working_dir) / "protocols" / f"{process_name}.py"
        if not self._is_valid_script_file(script_path):
            return False

        class_name = process_class_name(process_name)
        source = script_path.read_text(encoding="utf-8")
        new_source = (
            _remove_method(source, method_name, class_name)
            if removed
            else _add_method_stub(source, method_name, class_name)
        )
        if new_source == source:
            return False

        script_path.write_text(new_source, encoding="utf-8")
        if (
            self._script_editor is not None
            and self._script_editor.isVisible()
            and self._script_editor.editor.path == script_path
        ):
            self._script_editor.editor.clear_protected_zone()
            self._script_editor.editor.setText(new_source)
        return True

    def _inject_to_script(self, method_name: str, content: str) -> bool:
        orchestrator = getattr(self.parent_ref, "orchestrator", None)
        working_dir = getattr(orchestrator, "working_dir", None)
        process_name = self.model.process
        if not working_dir or not process_name:
            return False

        script_path = Path(working_dir) / "protocols" / f"{process_name}.py"
        if not self._is_valid_script_file(script_path):
            return False

        class_name = process_class_name(process_name)
        source = script_path.read_text(encoding="utf-8")
        new_source = _add_content_to_method(source, method_name, class_name, content)
        if new_source == source:
            return False

        script_path.write_text(new_source, encoding="utf-8")
        if (
            self._script_editor is not None
            and self._script_editor.isVisible()
            and self._script_editor.editor.path == script_path
        ):
            self._script_editor.editor.clear_protected_zone()
            self._script_editor.editor.setText(new_source)
        return True

    def _update_command_script(self, method_name: str, sig: CommandSignature) -> None:
        orchestrator = getattr(self.parent_ref, "orchestrator", None)
        working_dir = getattr(orchestrator, "working_dir", None)
        process_name = self.model.process
        if not working_dir or not process_name:
            return
        script_path = Path(working_dir) / "protocols" / f"{process_name}.py"
        if not self._is_valid_script_file(script_path):
            return
        class_name = process_class_name(process_name)
        source = script_path.read_text(encoding="utf-8")
        new_source = _replace_method_body(
            source, method_name, class_name, sig.line_script
        )
        if new_source == source:
            return
        script_path.write_text(new_source, encoding="utf-8")
        if (
            self._script_editor is not None
            and self._script_editor.isVisible()
            and self._script_editor.editor.path == script_path
        ):
            self._script_editor.editor.clear_protected_zone()
            self._script_editor.editor.setText(new_source)

    def _convert_command_to_script(self, data: BlockData) -> None:
        data.block_tag = ProtocolBlock.SCRIPT
        self.controller.block_updated.emit(data.node_id)
        if self._script_editor is not None:
            self._script_editor.focus_method(data.method)
            self._script_editor.show()
            self._script_editor.raise_()
            self._script_editor.activateWindow()

    def access_process_parameters(self) -> None:
        orchestrator = getattr(self.parent_ref, "orchestrator", None)
        working_dir = getattr(orchestrator, "working_dir", None)
        process_name = self.model.process
        if not working_dir or not process_name:
            return

        script_path = Path(working_dir) / "protocols" / f"{process_name}.py"
        if not self._is_valid_script_file(script_path):
            return

        class_name = process_config_class_name(process_name)
        if self._parameters_editor is not None and self._parameters_editor_target != (
            script_path,
            class_name,
        ):
            self._dispose_auxiliary_window("_parameters_editor")
            self._parameters_editor_target = None

        if self._parameters_editor is None:
            self._parameters_editor = MainParametersEditor(
                path=script_path,
                class_name=class_name,
                parent=self,
            )
            self._parameters_editor_target = (script_path, class_name)

        self._dispose_auxiliary_window("_script_editor")

        self._parameters_editor.show()
        self._parameters_editor.raise_()
        self._parameters_editor.activateWindow()
