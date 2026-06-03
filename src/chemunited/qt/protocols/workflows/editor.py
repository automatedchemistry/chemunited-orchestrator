import ast
import textwrap
from pathlib import Path

from loguru import logger
from PyQt5 import sip
from PyQt5.Qsci import QsciScintilla
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QDropEvent, QKeyEvent
from PyQt5.QtWidgets import QWidget

from chemunited.qt.shared.editor.protocols.script import (
    ScriptEditor,
    ScriptEditorWindow,
)


class ProtectedZoneEditor(ScriptEditor):
    """EditorBase subclass with per-range read-only protection and visual dimming."""

    _DIM_INDICATOR: int = 8  # INDIC_CONTAINER — first app-reserved Scintilla slot
    _DIM_ALPHA: int = 18
    _FOCUS_MARKER: int = 0
    _FOCUS_MARGIN: int = 1
    _FOCUS_MARGIN_WIDTH: int = 5
    _FOCUS_COLOR: QColor = QColor("#3A7AFE")

    def __init__(self, path: Path, parent=None) -> None:
        super().__init__(parent=parent, path=path)
        self._protected: bool = False
        self._body_start: int = 0
        self._body_end: int = 0
        self._prev_line_count: int = 0
        self._setup_dim_indicator()
        self._setup_focus_margin()
        self.linesChanged.connect(self._on_lines_changed)

    def _setup_dim_indicator(self) -> None:
        self.indicatorDefine(QsciScintilla.FullBoxIndicator, self._DIM_INDICATOR)
        self.setIndicatorDrawUnder(self._DIM_INDICATOR, True)
        self.setIndicatorForegroundColor(QColor(128, 128, 128), self._DIM_INDICATOR)
        self.SendScintilla(
            QsciScintilla.SCI_INDICSETALPHA,
            self._DIM_INDICATOR,
            self._DIM_ALPHA,
        )

    def _setup_focus_margin(self) -> None:
        self.setMarginType(self._FOCUS_MARGIN, QsciScintilla.SymbolMargin)
        self.setMarginWidth(self._FOCUS_MARGIN, self._FOCUS_MARGIN_WIDTH)
        self.setMarginMarkerMask(self._FOCUS_MARGIN, 1 << self._FOCUS_MARKER)
        self.markerDefine(QsciScintilla.SC_MARK_FULLRECT, self._FOCUS_MARKER)
        self.setMarkerBackgroundColor(self._FOCUS_COLOR, self._FOCUS_MARKER)
        self.setMarkerForegroundColor(self._FOCUS_COLOR, self._FOCUS_MARKER)

    def set_protected_zone(self, body_start: int, body_end: int) -> None:
        self._protected = True
        self._body_start = body_start
        self._body_end = body_end
        self._prev_line_count = self.lines()
        self._apply_dim_overlay()
        self._apply_focus_markers()

    def clear_protected_zone(self) -> None:
        self._protected = False
        self.markerDeleteAll(self._FOCUS_MARKER)
        last = self.lines() - 1
        if last >= 0:
            self.clearIndicatorRange(
                0, 0, last, self.lineLength(last), self._DIM_INDICATOR
            )

    def _apply_dim_overlay(self) -> None:
        last = self.lines() - 1
        if last < 0:
            return
        self.clearIndicatorRange(0, 0, last, self.lineLength(last), self._DIM_INDICATOR)
        if not self._protected:
            return
        if self._body_start > 0:
            before_end = self._body_start - 1
            self.fillIndicatorRange(
                0, 0, before_end, self.lineLength(before_end), self._DIM_INDICATOR
            )
        if self._body_end < last:
            after_start = self._body_end + 1
            self.fillIndicatorRange(
                after_start, 0, last, self.lineLength(last), self._DIM_INDICATOR
            )

    def _on_lines_changed(self) -> None:
        if not self._protected:
            return
        delta = self.lines() - self._prev_line_count
        if delta != 0:
            self._body_end += delta
            self._prev_line_count = self.lines()
            self._apply_dim_overlay()
            self._apply_focus_markers()

    def _apply_focus_markers(self) -> None:
        self.markerDeleteAll(self._FOCUS_MARKER)
        if not self._protected:
            return

        last = self.lines() - 1
        if last < 0:
            return

        start = max(self._body_start, 0)
        end = min(self._body_end, last)
        for line in range(start, end + 1):
            self.markerAdd(line, self._FOCUS_MARKER)

    def _is_in_editable_zone(self, line: int) -> bool:
        if not self._protected:
            return True
        return self._body_start <= line <= self._body_end

    def _selection_touches_protected(self) -> bool:
        line_from, _, line_to, _ = self.getSelection()
        if line_from == -1:
            return False
        for line in range(line_from, line_to + 1):
            if not self._is_in_editable_zone(line):
                return True
        return False

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if not self._protected:
            super().keyPressEvent(event)
            return

        key = event.key()
        mods = event.modifiers()
        ctrl = bool(mods & Qt.ControlModifier)

        # Always allow: navigation, undo/redo, copy, select-all, find
        if (
            key
            in (
                Qt.Key.Key_Left,
                Qt.Key.Key_Right,
                Qt.Key.Key_Up,
                Qt.Key.Key_Down,
                Qt.Key.Key_Home,
                Qt.Key.Key_End,
                Qt.Key.Key_PageUp,
                Qt.Key.Key_PageDown,
                Qt.Key.Key_Escape,
            )
            or (ctrl and key in (Qt.Key.Key_Z, Qt.Key.Key_Y))
            or (ctrl and key == Qt.Key.Key_C)
            or (ctrl and key == Qt.Key.Key_A)
            or (ctrl and key == Qt.Key.Key_F)
        ):
            super().keyPressEvent(event)
            return

        cur_line, cur_col = self.getCursorPosition()

        # Backspace at col 0 would merge with the line above
        if key == Qt.Key.Key_Backspace:
            if (
                cur_col == 0
                and cur_line > 0
                and not self._is_in_editable_zone(cur_line - 1)
            ):
                event.ignore()
                return
            if not self._is_in_editable_zone(cur_line):
                event.ignore()
                return

        # Delete at EOL would merge with the line below
        elif key == Qt.Key.Key_Delete:
            if not self._is_in_editable_zone(cur_line):
                event.ignore()
                return
            line_len = self.lineLength(cur_line)
            # lineLength includes the newline char; at EOL the cursor is at len-1
            if cur_line < self.lines() - 1 and cur_col >= line_len - 1:
                if not self._is_in_editable_zone(cur_line + 1):
                    event.ignore()
                    return

        elif not self._is_in_editable_zone(cur_line):
            event.ignore()
            return

        if self._selection_touches_protected():
            event.ignore()
            return

        super().keyPressEvent(event)

    def paste(self) -> None:
        if self._protected:
            cur_line, _ = self.getCursorPosition()
            if (
                not self._is_in_editable_zone(cur_line)
                or self._selection_touches_protected()
            ):
                return
        super().paste()

    def dropEvent(self, event: QDropEvent) -> None:
        if self._protected:
            pos = self.SendScintilla(
                QsciScintilla.SCI_POSITIONFROMPOINT,
                event.pos().x(),
                event.pos().y(),
            )
            line = self.SendScintilla(QsciScintilla.SCI_LINEFROMPOSITION, pos)
            if not self._is_in_editable_zone(line):
                event.ignore()
                return
        super().dropEvent(event)


class ProcessScriptEditorWindow(ScriptEditorWindow):
    """Process-specific script editor window with useful methods for the orchestrator."""

    def __init__(
        self,
        path: Path,
        class_name: str,
        main_parameters_path: Path | None = None,
        parent: QWidget | None = None,
    ):
        self._class_name = class_name
        self._current_focused_method: str | None = None
        super().__init__(
            path=path,
            class_name=class_name,
            main_parameters_path=main_parameters_path,
            parent=parent,
        )

    def _make_editor(self, path: Path) -> ProtectedZoneEditor:
        return ProtectedZoneEditor(path=path, parent=self)

    def focus_method(self, name: str) -> None:
        """Focus the editor on a specific method and protect all other lines."""
        self._current_focused_method = name

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

        body_start = (
            max(method_node.body[0].lineno - 1, 0) if method_node.body else line
        )
        body_end = max(
            (
                method_node.end_lineno
                or (
                    method_node.body[0].lineno
                    if method_node.body
                    else method_node.lineno
                )
            )
            - 1,
            0,
        )
        self._collapse_to_focused_method(tree, class_node, method_node)
        self.editor.set_protected_zone(body_start, body_end)

        # Defer until Scintilla has finished building fold levels for freshly
        # loaded text. Applying the folds too early can leave the target method
        # hidden until the user manually collapses and expands the class.
        #
        # ensureLineVisible only unfolds;
        # SCI_SCROLLCARET is needed to actually scroll the viewport to the cursor.
        def _apply() -> None:
            if sip.isdeleted(self) or sip.isdeleted(self.editor):
                return
            if self._current_focused_method != name:
                return

            self._collapse_to_focused_method(tree, class_node, method_node)
            self._reveal_focused_method(class_node, method_node)
            self.editor.setCursorPosition(line, index)
            self.editor.ensureLineVisible(line)
            self.editor.SendScintilla(QsciScintilla.SCI_SCROLLCARET)
            self.editor.setFocus()

        QTimer.singleShot(50, _apply)

    def _collapse_to_focused_method(
        self,
        tree: ast.Module,
        class_node: ast.ClassDef | None,
        method_node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> None:
        keep_expanded = {id(method_node)}
        if class_node is not None:
            keep_expanded.add(id(class_node))

        collapsed_lines = [
            node.lineno - 1
            for node in ast.walk(tree)
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and id(node) not in keep_expanded
        ]
        self.editor.setContractedFolds(collapsed_lines)

    def _reveal_focused_method(
        self,
        class_node: ast.ClassDef | None,
        method_node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> None:
        """Force the class header and target method block to be visible."""
        if class_node is not None:
            class_line = max(class_node.lineno - 1, 0)
            self.editor.SendScintilla(
                QsciScintilla.SCI_SETFOLDEXPANDED,
                class_line,
                True,
            )
            self._show_lines(class_line, class_line)

        method_line = max(method_node.lineno - 1, 0)
        method_end = max(
            (method_node.end_lineno or method_node.lineno) - 1, method_line
        )
        self.editor.SendScintilla(
            QsciScintilla.SCI_SETFOLDEXPANDED,
            method_line,
            True,
        )
        self._show_lines(method_line, method_end)

    def _show_lines(self, start: int, end: int) -> None:
        last = self.editor.lines() - 1
        if last < 0:
            return

        visible_start = min(max(start, 0), last)
        visible_end = min(max(end, visible_start), last)
        self.editor.SendScintilla(
            QsciScintilla.SCI_SHOWLINES,
            visible_start,
            visible_end,
        )

    def format_with_black(self) -> None:
        was_protected = self.editor._protected
        method_name = self._current_focused_method
        self.editor.clear_protected_zone()
        super().format_with_black()
        if was_protected and method_name:
            self.focus_method(method_name)

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
        self.editor.clear_protected_zone()
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


if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv)
    window = ProcessScriptEditorWindow(
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
