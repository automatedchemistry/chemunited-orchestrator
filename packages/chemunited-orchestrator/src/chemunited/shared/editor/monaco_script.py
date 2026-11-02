"""Monaco-based ScriptEditor with drop support."""

import ast
import json
import textwrap
from pathlib import Path

from PyQt5.QtCore import pyqtSignal

from chemunited.shared.editor.monaco_base import MonacoEditorBase
from chemunited.shared.editor.parameters.drag_list import ParameterDragableList
from chemunited.shared.editor.protocols.command_list import CommandList


def _drop_text_from_mime(mime_data: dict) -> str | None:
    """Extract text from drop MIME data."""
    # Check for custom MIME types first
    for mime_type in (CommandList.MIME, ParameterDragableList.MIME):
        if mime_type in mime_data.get("types", []):
            text = mime_data.get("data", {}).get(mime_type, "").strip()
            if text:
                return text

    # Fall back to plain text
    text_data = mime_data.get("data", {}).get("text/plain", "")
    if text_data:
        return text_data.strip()

    return None


def _find_function_for_line(
    tree: ast.AST,
    line_1based: int,
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    """Find the function containing a specific line."""
    matches = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.lineno <= line_1based <= (node.end_lineno or node.lineno)
    ]
    if not matches:
        return None
    return max(matches, key=lambda node: (node.lineno, node.col_offset))


def _line_indent(lines: list[str], line: int, fallback_col: int) -> str:
    """Get indentation for a specific line."""
    if 0 <= line < len(lines):
        text = lines[line]
        return text[: len(text) - len(text.lstrip(" \t"))]
    return " " * fallback_col


def _insertion_for_method_end_drop(
    source: str,
    drop_line: int,
) -> tuple[int, str] | None:
    """Find insertion point for dropped content at method end."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    function_node = _find_function_for_line(tree, drop_line + 1)
    if function_node is None or not function_node.body:
        return None

    lines = source.splitlines()
    first_body = function_node.body[0]
    first_body_line = first_body.lineno - 1
    first_body_indent = _line_indent(lines, first_body_line, first_body.col_offset)

    if (
        not function_node.lineno
        <= drop_line + 1
        <= (function_node.end_lineno or function_node.lineno)
    ):
        return None

    last_statement = function_node.body[-1]
    if isinstance(last_statement, ast.Return):
        return last_statement.lineno - 1, first_body_indent
    return last_statement.end_lineno or last_statement.lineno, first_body_indent


def _build_statement_insert_text(snippet: str, indent: str, newline: str) -> str:
    """Build properly indented statement text."""
    normalized = textwrap.dedent(snippet.strip()).strip("\r\n")
    lines = normalized.splitlines() or [normalized]
    return (
        newline.join(f"{indent}{line}" if line.strip() else "" for line in lines)
        + newline
    )


class MonacoScriptEditor(MonacoEditorBase):
    """Monaco-based ScriptEditor with drop support for commands and parameters."""

    drop_accepted = pyqtSignal()

    def __init__(self, path: Path, parent=None):
        super().__init__(parent=parent, path=path)

        # Connect drop handler
        self.bridge.dropReceived.connect(self._handle_drop)

    def _handle_drop(self, drop_data_json: str) -> None:
        """Handle drop event from Monaco Editor."""
        try:
            drop_data = json.loads(drop_data_json)
        except json.JSONDecodeError:
            return

        snippet = _drop_text_from_mime(drop_data)
        if snippet is None:
            return

        drop_line = drop_data.get("line", 0)
        source = self.text()

        insertion = _insertion_for_method_end_drop(source, drop_line)
        if insertion is None:
            return

        insert_line, indent = insertion
        newline = "\r\n" if "\r\n" in source else "\n"

        insert_text = _build_statement_insert_text(snippet, indent, newline)
        self.insertAt(insert_text, insert_line, 0)

        self.drop_accepted.emit()


if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication
    from qfluentwidgets import Theme, setTheme

    app = QApplication(sys.argv)
    setTheme(Theme.DARK)

    file = Path(__file__).parent / "protocols" / "example.py"
    editor = MonacoScriptEditor(path=file)
    editor.resize(800, 600)
    editor.show()

    sys.exit(app.exec_())
