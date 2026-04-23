import ast
import textwrap
from pathlib import Path

from loguru import logger
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QVBoxLayout, QWidget

from chemunited.qt.shared.editor.protocols.script import ScriptEditorWindow


class ProcessScriptEditorWindow(ScriptEditorWindow):
    """
    Process-specific script editor window with useful methods for the orchestrator.
    """

    def __init__(self, path: Path, class_name: str, parent: QWidget | None = None):
        """
        Initialize the ProcessScriptEditorWindow.
        
        Args:
            path: Initial path to the script file
            class_name: Name of the class
            parent: Parent widget
        """
        self._class_name = class_name
        super().__init__(path=path, parent=parent)
    
    def focus_method(self, name: str):
        """
        Focus the editor on a specific method.
        """
        code = self.editor.text()
        try:
            tree = ast.parse(code)
        except SyntaxError as exc:
            logger.opt(exception=exc).error(
                "Unable to focus method '{}' because the editor content is not "
                "valid Python.",
                name,
            )
            return

        class_node = next(
            (
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.ClassDef) and node.name == self._class_name
            ),
            None,
        )
        method_node = None
        if class_node is not None:
            method_node = next(
                (
                    node
                    for node in class_node.body
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and node.name == name
                ),
                None,
            )

        if method_node is None:
            method_node = next(
                (
                    node
                    for node in ast.walk(tree)
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and node.name == name
                ),
                None,
            )

        if method_node is None:
            logger.error(
                "Method '{}.{}' was not found in '{}'.",
                self._class_name,
                name,
                self.editor.path,
            )
            return

        target_node = method_node.body[0] if method_node.body else method_node
        line = max(target_node.lineno - 1, 0)
        index = max(target_node.col_offset, 0)
        self.editor.setCursorPosition(line, index)
        self.editor.ensureLineVisible(line)
        self.editor.setFocus()
    
    def add_content(self, method: str, content: str):
        """
        Add content to a specific method of a class object.
        
        Args:
            method: Name of the method
            content: Content to add
        """
        if not content.strip():
            return

        code = self.editor.text()
        try:
            tree = ast.parse(code)
        except SyntaxError as exc:
            logger.opt(exception=exc).error(
                "Unable to add content to method '{}' because the editor content "
                "is not valid Python.",
                method,
            )
            return

        class_node = next(
            (
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.ClassDef) and node.name == self._class_name
            ),
            None,
        )
        if class_node is None:
            logger.error("Class '{}' was not found in '{}'.", self._class_name, self.editor.path)
            return

        method_node = next(
            (
                node
                for node in class_node.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == method
            ),
            None,
        )
        if method_node is None or not method_node.body:
            logger.error(
                "Method '{}.{}' was not found in '{}'.",
                self._class_name,
                method,
                self.editor.path,
            )
            return

        newline = "\r\n" if "\r\n" in code else "\n"
        body_indent = " " * method_node.body[0].col_offset
        normalized_content = textwrap.dedent(content).strip("\r\n")
        formatted_content = newline.join(
            f"{body_indent}{line}" if line else ""
            for line in normalized_content.splitlines()
        )

        lines = code.splitlines(keepends=True)
        insert_line = method_node.end_lineno or len(lines)
        lines.insert(insert_line, f"{newline}{formatted_content}")
        self.editor.setText("".join(lines))
        self.editor.setCursorPosition(insert_line, len(body_indent))

    def get_method_block(self, name: str) -> str | None:
        """
        Get the content of a specific method.
        
        Args:
            name: Name of the method
        """
        try:
            source = self.editor.path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return ""

        try:
            tree = ast.parse(source)
        except SyntaxError:
            return ""

        matches = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == name
        ]
        if not matches:
            return ""

        def _start_lineno(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
            if node.decorator_list:
                return node.decorator_list[0].lineno
            return node.lineno

        matches.sort(key=lambda node: (_start_lineno(node), node.col_offset))
        target = matches[0]
        lines = source.splitlines(keepends=True)
        return "".join(lines[_start_lineno(target) - 1 : target.end_lineno]).rstrip()
