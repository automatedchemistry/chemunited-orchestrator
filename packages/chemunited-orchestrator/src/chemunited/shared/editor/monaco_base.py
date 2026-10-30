"""Monaco Editor integration with PyQt5 using QWebEngineView."""

import json
from pathlib import Path
from typing import Any, Callable

from PyQt5.QtCore import QObject, QTimer, QUrl, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import QVBoxLayout, QWidget

try:
    from PyQt5.QtWebChannel import QWebChannel
    from PyQt5.QtWebEngineWidgets import (
        QWebEnginePage,
        QWebEngineScript,
        QWebEngineView,
    )

    WEBENGINE_AVAILABLE = True
except ImportError:
    WEBENGINE_AVAILABLE = False
    QWebEngineView = object  # type: ignore
    QWebEnginePage = object  # type: ignore
    QWebEngineScript = object  # type: ignore
    QWebChannel = object  # type: ignore

from loguru import logger


class MonacoBridge(QObject):
    """Bridge object for Python-JavaScript communication."""

    textChanged = pyqtSignal(str)  # full editor content
    cursorPositionChanged = pyqtSignal(int, int)  # line, column (0-based)
    editorFocused = pyqtSignal()
    saveFileRequested = pyqtSignal(str, str)  # content, path
    dropReceived = pyqtSignal(str)  # JSON-encoded drop data

    def __init__(self, editor: "MonacoEditorBase"):
        super().__init__()
        self.editor = editor
        self._save_callback: Callable[[str, str], tuple[bool, str]] | None = None

    def set_save_callback(
        self, callback: Callable[[str, str], tuple[bool, str]]
    ) -> None:
        """Set callback for file save operations."""
        self._save_callback = callback

    # NOTE: every method callable from JavaScript must be a @pyqtSlot —
    # QWebChannel only exposes slots and signals, not plain Python methods.

    @pyqtSlot(str, str)
    def onTextChanged(self, path: str, content: str) -> None:
        """Called when editor content changes (file path + new content)."""
        try:
            self.editor._on_text_changed(path, content)
        except Exception:
            logger.exception("onTextChanged slot failed")

    @pyqtSlot(str, str)
    def onActiveFileChanged(self, path: str, content: str) -> None:
        """Called when the user switches tabs in the JS tab bar."""
        try:
            self.editor._on_js_active_file_changed(path, content)
        except Exception:
            logger.exception("onActiveFileChanged slot failed")

    @pyqtSlot(int, int)
    def onCursorPositionChanged(self, line: int, column: int) -> None:
        """Called when cursor moves. QWebChannel entry point."""
        try:
            self.editor._on_js_cursor_changed(int(line), int(column))
        except Exception:
            logger.exception("onCursorPositionChanged slot failed")

    @pyqtSlot(int, int, int, int)
    def onSelectionChanged(
        self, start_line: int, start_col: int, end_line: int, end_col: int
    ) -> None:
        """Called when selection changes. QWebChannel entry point."""
        self.editor._cached_selection = (
            int(start_line),
            int(start_col),
            int(end_line),
            int(end_col),
        )

    # NOTE: slots that return a value to JavaScript MUST declare the return
    # type via ``result=`` — without it PyQt5 registers the slot as void and
    # QWebChannel resolves the JS promise with ``null`` instead of the JSON
    # string (which made readFile consumers crash on `res.ok`).

    @pyqtSlot(str, result="str")
    def readFile(self, path: str) -> str:
        """Read a file for opening in a new tab. Returns JSON {ok, content/error}."""
        try:
            content = Path(path).read_text(encoding="utf-8")
            return json.dumps({"ok": True, "content": content})
        except (OSError, UnicodeError) as exc:
            return json.dumps({"ok": False, "error": str(exc)})

    @pyqtSlot()
    def onEditorFocused(self) -> None:
        """Called when editor receives focus. QWebChannel entry point."""
        self.editorFocused.emit()

    @pyqtSlot(str, str)
    def saveFile(self, content: str, path: str) -> None:
        """Save file content to disk. Called from JavaScript."""
        if self._save_callback:
            ok, err = self._save_callback(content, path)
            if not ok:
                logger.error(f"Save failed: {err}")
            return
        try:
            Path(path).write_text(content, encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to save file: {e}")

    @pyqtSlot(object)
    def handleDrop(self, dropData: Any) -> None:
        """Handle drop event from JavaScript (dict or JSON string)."""
        if isinstance(dropData, str):
            self.dropReceived.emit(dropData)
        else:
            self.dropReceived.emit(json.dumps(dropData))


class MonacoEditorBase(QWidget):
    """
    Monaco-based source code editor using QWebEngineView.

    This class provides the same API as EditorBase but uses Monaco Editor
    (the same editor engine as VS Code) instead of QScintilla.

    Features:
    - IntelliSense and auto-completion
    - Syntax highlighting for Python
    - Code folding
    - Minimap
    - Auto-save
    - Dark/Light theme support
    """

    textChanged = pyqtSignal()
    editorFocused = pyqtSignal()
    dropAccepted = pyqtSignal()
    active_file_changed = pyqtSignal(str)  # new active file path (tabs)
    editor_ready = pyqtSignal()  # emitted once the Monaco page is usable

    AUTOSAVE_INTERVAL_MS = 2000

    def __init__(
        self,
        parent: QWidget | None,
        path: Path,
    ):
        super().__init__(parent)

        if not WEBENGINE_AVAILABLE:
            raise ImportError(
                "PyQt5.QtWebEngineWidgets is required for Monaco Editor. "
                "Install it with: pip install PyQtWebEngine. "
                "Note: it must be imported BEFORE QApplication is created "
                "(import PyQt5.QtWebEngineWidgets early in your entry point)."
            )

        self.path = path
        self.full_path = path.absolute()
        self._current_file_changed = False
        self._autosave_enabled = True

        # Synchronous caches (runJavaScript callbacks are async in PyQt5,
        # so Python-side getters read these caches instead)
        self._cached_text: str = ""
        self._cached_line: int = 0
        self._cached_col: int = 0
        self._cached_selection: tuple[int, int, int, int] = (0, 0, 0, 0)
        self._editor_ready: bool = False

        # Setup layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Create web view
        self.web_view = QWebEngineView(self)
        layout.addWidget(self.web_view)

        # Setup web channel for JS-Python communication
        self.bridge = MonacoBridge(self)
        self.bridge.set_save_callback(self._write_to_disk)
        self.bridge.editorFocused.connect(self.editorFocused.emit)

        self.channel = QWebChannel(self)
        self.channel.registerObject("pybridge", self.bridge)

        # Channel MUST be attached before the page loads, otherwise the
        # page never sees qt.webChannelTransport
        page = self.web_view.page()
        if page is not None:
            page.setWebChannel(self.channel)

        # Load the editor page
        self._load_editor()

        # Re-theme the Monaco page live when the app theme changes.
        # Skipped until the page is ready (_on_load_finished re-applies).
        from chemunited.shared.widgets.app_theme import register_theme_observer

        register_theme_observer(self._on_app_theme_changed)

    def _load_editor(self) -> None:
        """Load Monaco Editor HTML and initialize."""
        # Get the HTML file path
        resources_dir = Path(__file__).parent.parent / "resources" / "monaco"
        html_path = resources_dir / "editor.html"

        if not html_path.exists():
            logger.error(f"Monaco editor HTML not found at {html_path}")
            return

        # Load local HTML file
        self.web_view.setUrl(QUrl.fromLocalFile(str(html_path)))

        # Notify after page load
        self.web_view.loadFinished.connect(self._on_load_finished)

    def _on_load_finished(self, ok: bool) -> None:
        """Called when page finishes loading."""
        if not ok:
            logger.error("Failed to load Monaco editor page")
            return

        # Set theme based on system
        from qfluentwidgets import isDarkTheme

        theme = "dark" if isDarkTheme() else "light"
        self._set_theme(theme)

        # Monaco may still be loading its bundles; poll until ready, then
        # hand the page its initial file.
        self._init_attempts = 0
        self._initialize_page()

    def _initialize_page(self) -> None:
        """Wait for monacoEditor API, then push the initial file."""

        def on_ready(value: Any) -> None:
            if value:
                self._load_content()
                self._editor_ready = True
                self.editor_ready.emit()
            elif self._init_attempts < 40:  # ~10s total
                self._init_attempts += 1
                QTimer.singleShot(250, self._initialize_page)
            else:
                logger.error("Monaco editor did not become ready in time")

        page = self.web_view.page()
        if page is not None:
            page.runJavaScript(
                "typeof monacoEditor !== 'undefined' && !!monacoEditor.openFile",
                on_ready,
            )

    def _load_content(self) -> None:
        """Load the initial file into a tab (content read from disk)."""
        try:
            content = self.path.read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to load file content: {e}")
            content = "# Error loading file"
        self._cached_text = content
        self._call_js(
            "monacoEditor.openFileInitial("
            f"{json.dumps(str(self.path))}, {json.dumps(content)})"
        )

    def _call_js(self, code: str) -> None:
        """Execute JavaScript code in the web view."""
        page = self.web_view.page()
        if page is not None:
            page.runJavaScript(code)

    def open_file(self, path: Path) -> None:
        """Open/activate a file in a new or existing tab.

        Updates Python-side state synchronously so callers (workflow frames,
        metadata) can rely on .path immediately; JS confirms with
        onActiveFileChanged once the tab is actually switched.
        """
        path = Path(path)
        if path == self.path:
            self._call_js(f"monacoEditor.openFile({json.dumps(str(path))})")
            return

        self.path = path
        self.full_path = path.absolute()
        self._current_file_changed = False
        self._cached_line = 0
        self._cached_col = 0
        try:
            self._cached_text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            self._cached_text = ""
        self.active_file_changed.emit(str(path))
        self._call_js(f"monacoEditor.openFile({json.dumps(str(path))})")

    def _on_text_changed(self, path: str, content: str) -> None:
        """Handle text change event from JavaScript (path + new content)."""
        if path != str(self.path):
            return  # edit belongs to a background tab; cache tracks active file
        self._cached_text = content
        self._current_file_changed = True
        self.textChanged.emit()

    def _on_js_active_file_changed(self, path: str, content: str) -> None:
        """Handle tab switch from JavaScript."""
        new_path = Path(path)
        if new_path == self.path:
            # Same file re-activated: just refresh the content cache
            self._cached_text = content
            return
        self.path = new_path
        self.full_path = new_path.absolute()
        self._cached_text = content
        self._current_file_changed = False
        self._cached_line = 0
        self._cached_col = 0
        self._cached_selection = (0, 0, 0, 0)
        self.active_file_changed.emit(path)

    def _on_js_cursor_changed(self, line: int, column: int) -> None:
        """Handle cursor move event from JavaScript."""
        self._cached_line = line
        self._cached_col = column

    def text(self) -> str:
        """Get current editor text (synchronous cache updated by JS events)."""
        return self._cached_text

    def setText(self, text: str) -> None:
        """Set editor text."""
        self._cached_text = text
        escaped = json.dumps(text)
        self._call_js(f"monacoEditor.setText({escaped})")
        self._current_file_changed = False

    def getCursorPosition(self) -> tuple[int, int]:
        """Get current cursor position (line, column), 0-based."""
        return (self._cached_line, self._cached_col)

    def setCursorPosition(self, line: int, column: int) -> None:
        """Set cursor position."""
        self._cached_line = line
        self._cached_col = column
        self._call_js(f"monacoEditor.setCursorPosition({line}, {column})")

    def insertAt(self, text: str, line: int, column: int) -> None:
        """Insert text at specified position."""
        escaped = json.dumps(text)
        self._call_js(f"monacoEditor.insertAt({escaped}, {line}, {column})")
        # Optimistically update cache; JS will confirm via onTextChanged
        lines = self._cached_text.splitlines(keepends=True)
        if 0 <= line < len(lines):
            new_line = lines[line][:column] + text + lines[line][column:]
            lines[line] = new_line
            self._cached_text = "".join(lines)

    def getSelection(self) -> tuple[int, int, int, int]:
        """Get selection (startLine, startCol, endLine, endCol), 0-based."""
        return self._cached_selection

    def set_autosave(self, enabled: bool) -> None:
        """Enable or disable autosave."""
        self._autosave_enabled = enabled
        self._call_js(f"monacoEditor.setAutosave({str(enabled).lower()})")

    def autosave(self) -> None:
        """Trigger autosave."""
        if self._autosave_enabled and self._current_file_changed:
            self._call_js("monacoEditor.saveFile()")

    def save_now(self) -> bool:
        """Manual save."""
        try:
            content = self.text()
            ok, _ = self._write_to_disk(content, str(self.full_path))
            if ok:
                self._current_file_changed = False
                self._call_js("monacoEditor.setDirty(false)")
            return ok
        except Exception as e:
            logger.error(f"Save failed: {e}")
            return False

    def _write_to_disk(self, content: str, path: str) -> tuple[bool, str]:
        """Write content to disk."""
        try:
            Path(path).write_text(content, encoding="utf-8")
            return True, ""
        except Exception as e:
            return False, str(e)

    def _set_theme(self, theme_name: str) -> None:
        """Set editor theme."""
        self._call_js(f"monacoEditor.setTheme('{theme_name}')")

    def _on_app_theme_changed(self) -> None:
        """Observer callback: re-apply the app theme to the Monaco page."""
        if not self._editor_ready:
            return
        from qfluentwidgets import isDarkTheme

        self._set_theme("dark" if isDarkTheme() else "light")

    def focus(self) -> None:
        """Focus the editor."""
        self._call_js("monacoEditor.focus()")
        self.web_view.setFocus()

    def setFocus(self) -> None:  # type: ignore[override]
        """Qt focus method."""
        super().setFocus()
        self.focus()

    def undo(self) -> None:
        """Undo last action."""
        self._call_js("monacoEditor.undo()")

    def redo(self) -> None:
        """Redo last action."""
        self._call_js("monacoEditor.redo()")

    def find(self) -> None:  # type: ignore[override]
        """Open find dialog."""
        self._call_js("monacoEditor.find()")

    def lines(self) -> int:
        """Get number of lines in editor (derived from cached text)."""
        if not self._cached_text:
            return 0
        return self._cached_text.count("\n") + 1

    def lineLength(self, line: int) -> int:
        """Get length of a specific line (derived from cached text)."""
        split = self._cached_text.splitlines()
        if 0 <= line < len(split):
            return len(split[line])
        return 0


if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication
    from qfluentwidgets import Theme, setTheme

    app = QApplication(sys.argv)
    setTheme(Theme.DARK)

    file = Path(__file__)
    editor = MonacoEditorBase(None, file)
    editor.resize(800, 600)
    editor.show()

    sys.exit(app.exec_())
