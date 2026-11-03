"""Monaco-based ScriptEditor with drop support."""

from pathlib import Path
from typing import Any

from PyQt5.QtCore import QMimeData, QPoint, pyqtSignal

from chemunited.shared.editor.monaco_base import MonacoEditorBase
from chemunited.shared.editor.parameters.drag_list import ParameterDragableList
from chemunited.shared.editor.protocols.command_list import CommandList
from chemunited.shared.editor.protocols.script import (
    _build_statement_insert_text,
    _drop_text_from_mime,
    _insertion_for_method_end_drop,
)


class MonacoScriptEditor(MonacoEditorBase):
    """Monaco-based ScriptEditor with drop support for commands and parameters."""

    drop_accepted = pyqtSignal()

    DROP_MIME_TYPES = (CommandList.MIME, ParameterDragableList.MIME)

    def __init__(self, path: Path, parent=None):
        super().__init__(parent=parent, path=path)

    def _handle_qt_drop(self, mime_data: QMimeData, pos: QPoint) -> None:
        """Insert a dragged command/parameter at the end of the method under it."""
        if mime_data.hasFormat(ParameterDragableList.MIME) and mime_data.hasFormat(
            ParameterDragableList.PATH_MIME
        ):
            source_path = Path(
                bytes(mime_data.data(ParameterDragableList.PATH_MIME)).decode("utf-8")
            ).resolve()
            if (
                source_path != self.path.resolve()
                and source_path.name != "main_parameters.py"
            ):
                return

        snippet = _drop_text_from_mime(mime_data)
        if snippet is None:
            return
        # Read everything from the MIME data now: it dies with the drag, and
        # the drop line only arrives later from JavaScript.
        is_command = mime_data.hasFormat(CommandList.MIME)

        page = self.web_view.page()
        if page is None:
            return
        page.runJavaScript(
            f"monacoEditor.lineAtPoint({pos.x()}, {pos.y()})",
            lambda target: self._insert_drop(snippet, is_command, target),
        )

    def _insert_drop(self, snippet: str, is_command: bool, target: Any) -> None:
        line = -1
        if isinstance(target, dict):
            if not target.get("editable", True):
                return  # dropped on a locked line
            line = int(target.get("line", -1))
        if line < 0:
            line = self.getCursorPosition()[0]

        source = self.text()
        insertion = _insertion_for_method_end_drop(source, line)
        if insertion is None:
            return

        insert_line, indent = insertion
        newline = "\r\n" if "\r\n" in source else "\n"
        self.insertAt(
            _build_statement_insert_text(snippet, indent, newline), insert_line, 0
        )
        if is_command:
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
