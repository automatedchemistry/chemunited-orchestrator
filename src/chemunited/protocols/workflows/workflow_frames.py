from __future__ import annotations

import ast
import textwrap
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import override

import black  # type: ignore[import-not-found]
from chemunited_core.protocols import CommandSignature
from chemunited_workflow.enums import NodeState
from loguru import logger
from PyQt5 import sip
from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QPainter, QPen
from PyQt5.QtWidgets import QFrame, QGraphicsItem, QGraphicsView
from qfluentwidgets import Action, InfoBar, InfoBarPosition, RoundMenu, isDarkTheme

from chemunited.project.storage import sync_process
from chemunited.protocols.workflows.naming import (
    process_class_name,
    process_config_class_name,
)
from chemunited.shared.editor.parameters.main import MainParametersEditor
from chemunited.shared.editor.protocols.command import CommandEditorDialog
from chemunited.shared.editor.protocols.command_list import CommandList
from chemunited.shared.enums import SetupStepMode, WindowCategory
from chemunited.shared.enums.protocols_enum import ProtocolBlock
from chemunited.shared.graph import GraphCore, SceneCore
from chemunited.shared.icon import OrchestratorIcon

from .controller import WorkflowController
from .editor import ProcessScriptEditorWindow
from .elements.access_point import WorkflowAccessPoints
from .elements.work_connection import WorkflowConnection
from .elements.work_node import WorkflowNode
from .exceptions import WorkflowRuleViolation
from .process_workflow import BlockData, ConnectionData
from .workflow_rules import resolve_render_start_role

COMMAND_BLOCK_GUIDANCE = (
    "# Keep this block limited to one platform command and `return True`."
)
LOOP_ITERATION_GUIDANCE = (
    "# ctx.iteration identifies the current workflow pass. It starts at 0 and",
    "# increases by 1 when a loopback starts another pass; it is not a local counter.",
)


@dataclass(frozen=True, slots=True)
class CommandBlockValidationError:
    line: int
    reason: str


def _format_python_source(source: str) -> str:
    try:
        return black.format_str(source, mode=black.Mode())
    except black.NothingChanged:
        return source
    except Exception as exc:
        logger.opt(exception=exc).error("Black formatting failed.")
        return source


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
    if (
        first_body > method_node.lineno
        and lines[first_body - 1].strip() == COMMAND_BLOCK_GUIDANCE
    ):
        first_body -= 1
    last_body = method_node.end_lineno
    normalized = textwrap.dedent(new_content).strip("\r\n")
    replacement = newline.join(
        f"{body_indent}{line}" if line else "" for line in normalized.splitlines()
    )
    replacement = f"{replacement}{newline}"
    lines[first_body:last_body] = [replacement]
    return "".join(lines)


def _ensure_method_comment(
    source: str,
    method_name: str,
    class_name: str,
    comment_lines: tuple[str, ...],
) -> str:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source
    class_node = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef) and node.name == class_name
        ),
        None,
    )
    if class_node is None:
        return source
    method_node = next(
        (
            node
            for node in class_node.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == method_name
        ),
        None,
    )
    if method_node is None or not method_node.body:
        return source

    lines = source.splitlines(keepends=True)
    method_source = "".join(
        lines[method_node.lineno - 1 : method_node.end_lineno]
    )
    if all(comment in method_source for comment in comment_lines):
        return source

    newline = "\r\n" if "\r\n" in source else "\n"
    indent = " " * method_node.body[0].col_offset
    comment = "".join(f"{indent}{line}{newline}" for line in comment_lines)
    lines.insert(method_node.body[0].lineno - 1, comment)
    return "".join(lines)


def _is_config_ref(node: ast.expr) -> str | None:
    """Return 'self.config.X' or 'self.main_parameters.X' if the node matches, else None."""
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Attribute)
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == "self"
        and node.value.attr in {"config", "main_parameters"}
    ):
        return f"self.{node.value.attr}.{node.attr}"
    return None


def _extract_model_fields(source: str, class_name: str) -> list[str]:
    """Return annotated field names of a Pydantic model class in source via AST (no import)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return [
                item.target.id
                for item in node.body
                if isinstance(item, ast.AnnAssign)
                and isinstance(item.target, ast.Name)
                and item.target.id != "model_config"
            ]
    return []


def _validate_command_block(source: str, method_name: str, class_name: str) -> tuple[
    tuple[str, str, str, dict[str, object], dict[str, str]] | None,
    CommandBlockValidationError | None,
]:
    from chemunited_quantities import ChemUnitQuantity

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return None, CommandBlockValidationError(
            exc.lineno or 1,
            f"The process file is not valid Python: {exc.msg}.",
        )

    class_node = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef) and node.name == class_name
        ),
        None,
    )
    if class_node is None:
        return None, CommandBlockValidationError(
            1,
            f"Class {class_name!r} was not found.",
        )

    method_node = next(
        (
            node
            for node in class_node.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == method_name
        ),
        None,
    )
    if method_node is None:
        return None, CommandBlockValidationError(
            class_node.lineno,
            f"Method {method_name!r} was not found in {class_name!r}.",
        )

    body = method_node.body
    expected_line = (method_node.end_lineno or method_node.lineno) + 1
    if not body:
        return None, CommandBlockValidationError(
            expected_line,
            "The command block is empty.",
        )

    command_statement = body[0]
    if (
        isinstance(command_statement, ast.Expr)
        and isinstance(command_statement.value, ast.Constant)
        and isinstance(command_statement.value.value, str)
    ):
        return None, CommandBlockValidationError(
            command_statement.lineno,
            "Docstrings are not allowed in command blocks; use a comment instead.",
        )
    if not (
        isinstance(command_statement, ast.Expr)
        and isinstance(command_statement.value, ast.Call)
    ):
        return None, CommandBlockValidationError(
            command_statement.lineno,
            "The first executable statement must be one platform command call.",
        )

    call = command_statement.value
    func = call.func
    if not (isinstance(func, ast.Attribute) and func.attr.lower() in {"get", "put"}):
        return None, CommandBlockValidationError(
            call.lineno,
            'Call self.platform["component"].get(...) or .put(...).',
        )

    subscript = func.value
    if not (
        isinstance(subscript, ast.Subscript)
        and isinstance(subscript.value, ast.Attribute)
        and isinstance(subscript.value.value, ast.Name)
        and subscript.value.value.id == "self"
        and subscript.value.attr == "platform"
        and isinstance(subscript.slice, ast.Constant)
        and isinstance(subscript.slice.value, str)
        and subscript.slice.value
    ):
        return None, CommandBlockValidationError(
            call.lineno,
            'Use a literal component name: self.platform["component"].put(...).',
        )

    if (
        len(call.args) != 1
        or not isinstance(call.args[0], ast.Constant)
        or not isinstance(call.args[0].value, str)
        or not call.args[0].value
    ):
        return None, CommandBlockValidationError(
            call.lineno,
            "Pass exactly one literal command name as the positional argument.",
        )

    eval_ns = {"ChemUnitQuantity": ChemUnitQuantity}
    kwargs: dict[str, object] = {}
    param_refs: dict[str, str] = {}
    for keyword in call.keywords:
        if keyword.arg is None:
            return None, CommandBlockValidationError(
                keyword.value.lineno,
                "Expanded keyword arguments (**kwargs) are not supported.",
            )
        ref = _is_config_ref(keyword.value)
        if ref is not None:
            param_refs[keyword.arg] = ref
            continue
        try:
            kwargs[keyword.arg] = ast.literal_eval(keyword.value)
        except (ValueError, TypeError):
            try:
                kwargs[keyword.arg] = eval(
                    ast.unparse(keyword.value),
                    eval_ns,
                )
            except Exception:
                return None, CommandBlockValidationError(
                    keyword.value.lineno,
                    f"Argument {keyword.arg!r} must use a supported literal value.",
                )

    if len(body) == 1:
        return None, CommandBlockValidationError(
            expected_line,
            "The command block must end with `return True`.",
        )
    if len(body) > 2:
        return None, CommandBlockValidationError(
            body[1].lineno,
            "Command blocks must contain exactly one platform call followed by "
            "`return True`; remove all additional executable statements.",
        )

    final_statement = body[1]
    if not (
        isinstance(final_statement, ast.Return)
        and isinstance(final_statement.value, ast.Constant)
        and final_statement.value.value is True
    ):
        return None, CommandBlockValidationError(
            final_statement.lineno,
            "The final statement must be exactly `return True`.",
        )

    return (
        subscript.slice.value,
        call.args[0].value,
        func.attr.upper(),
        kwargs,
        param_refs,
    ), None


def _parse_command_call(
    source: str, method_name: str, class_name: str
) -> tuple[str, str, str, dict[str, object], dict[str, str]] | None:
    parsed, _error = _validate_command_block(source, method_name, class_name)
    return parsed


def _build_command_model(
    source: str,
    method_name: str,
    class_name: str,
    sig_cls: type[CommandSignature] | None = None,
) -> "CommandSignature | None":

    parsed = _parse_command_call(source, method_name, class_name)
    if parsed is None:
        return None
    component_name, command_name, http_method, kwargs, param_refs = parsed

    def _find_sig_class(cmd: str, method: str, base=CommandSignature):
        matches: list[type[CommandSignature]] = []
        for sub in base.__subclasses__():
            command_info = sub.model_fields.get("command")
            method_info = sub.model_fields.get("method")
            if (
                command_info
                and command_info.default == cmd
                and method_info
                and method_info.default == method
            ):
                matches.append(sub)
            matches.extend(_find_sig_class(cmd, method, sub))
        return matches

    if sig_cls is None:
        matches = _find_sig_class(command_name, http_method)
        if matches:
            # Prefer the most specific subclass when multiple commands share a name.
            sig_cls = max(matches, key=lambda cls: len(cls.mro()))
    if sig_cls is None:
        return None

    try:
        instance = sig_cls.model_validate({"component": component_name, **kwargs})
        if param_refs:
            instance.param_refs = param_refs
        return instance
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
        self._script_sync_rollbacks: set[str] = set()

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
            parsed_command, validation_error = _validate_command_block(
                source,
                data.method,
                class_name,
            )
            if parsed_command is None:
                self._show_command_format_error(
                    data.method,
                    script_path,
                    validation_error
                    or CommandBlockValidationError(
                        1,
                        "The command block could not be parsed.",
                    ),
                )
                return
            component_name, command_name, http_method, _kwargs, _param_refs = parsed_command
            command = _build_command_model(
                source,
                data.method,
                class_name,
                sig_cls=self._resolve_command_signature_class(
                    component_name,
                    command_name,
                    http_method,
                ),
            )
            if command is None:
                command_line = self._command_call_line(
                    source,
                    data.method,
                    class_name,
                )
                self._show_command_editor_error(
                    title="Cannot open command editor",
                    message=(
                        f"Command block {data.method!r} has valid syntax, but "
                        f"{component_name!r}/{http_method} {command_name!r} could "
                        "not be matched to an available component command.\n"
                        f"File: {script_path.resolve()}\n"
                        f"Line: {command_line}"
                    ),
                )
                return
            config_fields = _extract_model_fields(source, "ProcessConfig")
            mp_path = script_path.parent / "main_parameters.py"
            main_params_fields = (
                _extract_model_fields(mp_path.read_text(encoding="utf-8"), "MainParameter")
                if mp_path.exists()
                else []
            )
            editor = CommandEditorDialog(
                function_name=data.method or "",
                command_model=command,
                label=data.label,
                description=data.description,
                config_fields=config_fields,
                main_params_fields=main_params_fields,
                parent=self,
            )
            editor.metadata_saved.connect(self._update_block_metadata)
            editor.saved.connect(
                lambda sig: self._update_command_script(data.method, sig)
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
            self._script_editor.metadata_saved.connect(self._update_block_metadata)

        if data.method:
            self._script_editor.set_node_metadata(
                data.node_id,
                data.label,
                data.description,
            )
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
        http_method: str | None = None,
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
            method_field = command_class.model_fields.get("method")
            if http_method is None or (
                method_field is not None and method_field.default == http_method
            ):
                return command_class

        for candidate in commands.values():
            if not (
                isinstance(candidate, type) and issubclass(candidate, CommandSignature)
            ):
                continue
            command_field = candidate.model_fields.get("command")
            method_field = candidate.model_fields.get("method")
            if (
                command_field is not None
                and command_field.default == command_name
                and method_field is not None
                and method_field.default == http_method
            ):
                return candidate
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
        if not self._add_command_block(scene_pos, line_script):
            event.ignore()
            return
        event.acceptProposedAction()

    def _add_command_block(self, scene_pos: QPointF, line_script: str) -> bool:
        block = self.controller.add_block(
            block_tag=ProtocolBlock.COMMAND,
            pos=(scene_pos.x(), scene_pos.y()),
        )
        if self.controller.get_block(block.node_id) is None:
            return False

        if self._inject_to_script(block.node_id, line_script):
            return True

        self.controller.remove_block(block.node_id)
        self._show_script_sync_error(
            f"Could not add {block.node_id!r} because its command could not "
            "be written to the process script."
        )
        return False

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
            action.triggered.connect(
                lambda _checked=False, tag=block_tag, pos=QPointF(scene_pos): (
                    self.add_block(tag, pos)
                )
            )
            menu.addAction(action)
        menu.addSeparator()
        open_process_parameters_action = Action(self)
        open_process_parameters_action.setText("Access Process Parameters")
        open_process_parameters_action.setIcon(OrchestratorIcon.VARIABLE.icon())
        open_process_parameters_action.triggered.connect(self.access_process_parameters)
        menu.addAction(open_process_parameters_action)

        access_simulation = Action(self)
        access_simulation.setText("Simulate Process")
        access_simulation.setIcon(OrchestratorIcon.SIMULATION.icon())
        access_simulation.triggered.connect(self.access_simulation)
        menu.addAction(access_simulation)

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

    def _display_text(self, block: BlockData) -> tuple[str, str]:
        name = block.node_id
        block_tag = block.block_tag
        labels = {
            ProtocolBlock.START: ("Start", "Entry"),
            ProtocolBlock.END: ("End", "Exit"),
            ProtocolBlock.SCRIPT: (name, "Module"),
            ProtocolBlock.LOOP: (name, "Repeat"),
            ProtocolBlock.IF: (name, "Branch"),
            ProtocolBlock.COMMAND: (name, "Command"),
        }
        title, subtitle = labels[block_tag]
        if block_tag not in {ProtocolBlock.START, ProtocolBlock.END}:
            title = name if block.label == name else f"{block.label} ({name})"
        return title, subtitle

    def _add_node_from_block(self, block: BlockData) -> WorkflowNode:
        title, subtitle = self._display_text(block)
        node = WorkflowNode(
            node_name=block.node_id,
            block_tag=block.block_tag,
            title=title,
            subtitle=subtitle,
            label=block.label,
            description=block.description,
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
            synced = self._sync_process_script()
            if synced and block.block_tag == ProtocolBlock.LOOP:
                synced = self._ensure_loop_iteration_guidance(block.method)
            if synced:
                return
            self._script_sync_rollbacks.add(name)
            try:
                self.controller.remove_block(name)
            finally:
                self._script_sync_rollbacks.discard(name)
            self._show_script_sync_error(
                f"Could not add {name!r} because the process script could not "
                "be updated safely."
            )

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
        title, _subtitle = self._display_text(block)
        node.update_metadata(title, block.label, block.description)
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
        self.scene_attribute.removeItem(node)
        if name in self._script_sync_rollbacks:
            return
        if (
            node.block_tag not in {ProtocolBlock.START, ProtocolBlock.END}
            and not self._sync_process_script()
        ):
            self._show_script_sync_error(
                f"Removed {name!r} from the graph, but the process script "
                "could not be updated safely."
            )

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

    def _sync_process_script(self) -> bool:
        orchestrator = getattr(self.parent_ref, "orchestrator", None)
        working_dir = getattr(orchestrator, "working_dir", None)
        process_name = self.model.process
        if not working_dir or not process_name:
            return False

        script_path = Path(working_dir) / "protocols" / f"{process_name}.py"
        try:
            synced = sync_process(Path(working_dir), process_name, self.model)
        except Exception as exc:
            logger.opt(exception=exc).error(
                f"Could not synchronize process script for {process_name!r}."
            )
            return False

        if not synced:
            logger.error(
                f"Could not synchronize process script for {process_name!r}; "
                "the existing file was left unchanged."
            )
            return False

        if (
            self._script_editor is not None
            and self._script_editor.isVisible()
            and self._script_editor.editor.path == script_path
        ):
            source = script_path.read_text(encoding="utf-8")
            self._script_editor.editor.clear_protected_zone()
            self._script_editor.editor.setText(source)
        return True

    def _ensure_loop_iteration_guidance(self, method_name: str) -> bool:
        orchestrator = getattr(self.parent_ref, "orchestrator", None)
        working_dir = getattr(orchestrator, "working_dir", None)
        process_name = self.model.process
        if not working_dir or not process_name:
            return False

        script_path = Path(working_dir) / "protocols" / f"{process_name}.py"
        if not self._is_valid_script_file(script_path):
            return False

        source = script_path.read_text(encoding="utf-8")
        updated = _ensure_method_comment(
            source,
            method_name,
            process_class_name(process_name),
            LOOP_ITERATION_GUIDANCE,
        )
        if updated == source:
            return all(comment in source for comment in LOOP_ITERATION_GUIDANCE)

        script_path.write_text(updated, encoding="utf-8")
        if (
            self._script_editor is not None
            and self._script_editor.isVisible()
            and self._script_editor.editor.path == script_path
        ):
            self._script_editor.editor.clear_protected_zone()
            self._script_editor.editor.setText(updated)
        return True

    def sync_script(self, method_name: str = "", removed: bool = False) -> bool:
        """Synchronize the complete process file.

        ``method_name`` and ``removed`` remain accepted for compatibility with
        callers of the previous method-only writer.
        """
        return self._sync_process_script()

    def _show_script_sync_error(self, message: str) -> None:
        logger.error(message)
        InfoBar.error(
            title="Process script not updated",
            content=message,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=5000,
            parent=self,
        )

    @staticmethod
    def _command_call_line(source: str, method_name: str, class_name: str) -> int:
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            return exc.lineno or 1
        class_node = next(
            (
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.ClassDef) and node.name == class_name
            ),
            None,
        )
        if class_node is None:
            return 1
        method_node = next(
            (
                node
                for node in class_node.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == method_name
            ),
            None,
        )
        if method_node is None or not method_node.body:
            return class_node.lineno
        return method_node.body[0].lineno

    @staticmethod
    def _command_block_example(method_name: str) -> str:
        return (
            f"def {method_name}(self, ctx: NodeExecutionContext) -> bool:\n"
            f"    {COMMAND_BLOCK_GUIDANCE}\n"
            '    self.platform["component"].put("command", ...)\n'
            "    return True"
        )

    def _show_command_editor_error(self, title: str, message: str) -> None:
        logger.warning(message)
        InfoBar.error(
            title=title,
            content=message,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=10000,
            parent=self,
        )

    def _show_command_format_error(
        self,
        method_name: str,
        script_path: Path,
        error: CommandBlockValidationError,
    ) -> None:
        message = (
            f"Command block {method_name!r} does not match the required format.\n"
            f"File: {script_path.resolve()}\n"
            f"Line: {error.line}\n"
            f"Reason: {error.reason}\n\n"
            "Expected format:\n"
            f"{self._command_block_example(method_name)}"
        )
        self._show_command_editor_error("Invalid command block", message)

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
        command_body = f"{COMMAND_BLOCK_GUIDANCE}\n{content}\nreturn True"
        new_source = _replace_method_body(
            source,
            method_name,
            class_name,
            command_body,
        )
        new_source = _format_python_source(new_source)
        if new_source == source:
            return False
        parsed, validation_error = _validate_command_block(
            new_source,
            method_name,
            class_name,
        )
        if parsed is None:
            logger.warning(
                f"Refused to write invalid command block {method_name!r}: "
                f"{validation_error}"
            )
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
        command_body = f"{COMMAND_BLOCK_GUIDANCE}\n{sig.line_script}\nreturn True"
        new_source = _replace_method_body(source, method_name, class_name, command_body)
        new_source = _format_python_source(new_source)
        if new_source == source:
            return
        parsed, validation_error = _validate_command_block(
            new_source,
            method_name,
            class_name,
        )
        if parsed is None:
            logger.warning(
                f"Refused to save invalid command block {method_name!r}: "
                f"{validation_error}"
            )
            return
        script_path.write_text(new_source, encoding="utf-8")
        if (
            self._script_editor is not None
            and self._script_editor.isVisible()
            and self._script_editor.editor.path == script_path
        ):
            self._script_editor.editor.clear_protected_zone()
            self._script_editor.editor.setText(new_source)

    def _update_block_metadata(
        self,
        node_id: str,
        label: str,
        description: str,
    ) -> None:
        self.controller.update_block_metadata(node_id, label, description)

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
    
    def access_simulation(self) -> None:
        if hasattr(self.parent_ref, "open_simulate_window"):
            self.parent_ref.open_simulate_window(self.model.process)
