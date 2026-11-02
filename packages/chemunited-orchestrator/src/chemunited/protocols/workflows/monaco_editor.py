"""Monaco-based ProcessScriptEditorWindow with method focusing."""

import ast
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QWidget

from chemunited.shared.editor.monaco_script import MonacoScriptEditor
from chemunited.shared.editor.protocols.script import ScriptEditorWindow

if TYPE_CHECKING:
    pass


class MonacoProcessScriptEditorWindow(ScriptEditorWindow):
    """
    Process-specific script editor window using Monaco Editor.

    Provides the same API as ProcessScriptEditorWindow but with Monaco Editor
    instead of QScintilla.
    """

    def __init__(
        self,
        path: Path,
        class_name: str,
        main_parameters_path: Path | None = None,
        parent: QWidget | None = None,
    ):
        self._class_name = class_name
        self._current_focused_method: str | None = None
        self._pending_focus_method: str | None = None
        super().__init__(
            path=path,
            class_name=class_name,
            main_parameters_path=main_parameters_path,
            parent=parent,
        )
        # Keep the window title in sync with the active tab (multi-file).
        self.editor.active_file_changed.connect(self._on_active_file_changed)
        # The Monaco page loads asynchronously: text()/AST parsing is only
        # reliable once the initial content has been pushed. Queue method
        # focusing that arrives too early and replay it when ready.
        self.editor.editor_ready.connect(self._on_editor_ready)

    def _on_editor_ready(self) -> None:
        """Apply a queued focus_method() once the Monaco page is ready."""
        if self._pending_focus_method is None:
            return
        name = self._pending_focus_method
        self._pending_focus_method = None
        self.focus_method(name)

    def _on_active_file_changed(self, path: str) -> None:
        """Update window title when the user switches tabs."""
        self.setWindowTitle(f"Script Editor: {path}")
        # The focused method belongs to the original file only; clear the
        # focus-method state when switching to another file.
        self._current_focused_method = None

    def open_file(self, path: Path, class_name: str | None = None) -> None:
        """Open/activate a script file in this window (new or existing tab).

        When the window is reused for a different process block, pass the
        new class_name so focus_method/AST lookups target the right class.
        """
        path = Path(path)
        self.editor.open_file(path)
        if class_name is not None:
            self._class_name = class_name
        self.setWindowTitle(f"Script Editor: {path}")
        # Parameter docks still describe the file this window was created
        # for; leave them untouched when opening a different file.

    def _make_editor(self, path: Path) -> MonacoScriptEditor:
        """Create Monaco script editor."""
        return MonacoScriptEditor(path=path, parent=self)

    def focus_method(self, name: str) -> None:
        """Move the cursor to a specific method (no code is highlighted or locked)."""
        self._current_focused_method = name

        if not getattr(self.editor, "_editor_ready", False):
            # The Monaco page (and therefore the text cache) is not loaded
            # yet; ast.parse("") finds no methods and would report a false
            # "method not found" error. Defer until the page is ready.
            self._pending_focus_method = name
            return

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

        def _apply() -> None:
            if self._current_focused_method != name:
                return

            self.editor.setCursorPosition(line, index)
            self.editor.focus()

        # Defer to ensure editor is ready
        QTimer.singleShot(100, _apply)

    def add_content(self, method: str, content: str) -> None:
        """Add content to a specific method of a class object."""
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
            logger.error(
                "Class '{}' was not found in '{}'.", self._class_name, self.editor.path
            )
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

        if self._current_focused_method == method:
            self.focus_method(method)

    def get_method_block(self, name: str) -> str | None:
        """Get the content of a specific method."""
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

    def format_with_black(self) -> None:
        """Apply Black formatting to the code."""
        super().format_with_black()


if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv)
    window = MonacoProcessScriptEditorWindow(
        Path(__file__).parent.parent.parent
        / "shared"
        / "editor"
        / "protocols"
        / "example.py",
        class_name="CustomProcess",
        main_parameters_path=Path(__file__).parent.parent.parent
        / "shared"
        / "editor"
        / "parameters"
        / "example.py",
    )
    window.focus_method("check_pressure")
    window.show()
    sys.exit(app.exec_())
