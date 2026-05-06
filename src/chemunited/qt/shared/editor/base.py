from pathlib import Path

from loguru import logger
from PyQt5.Qsci import QsciScintilla
from PyQt5.QtCore import QIODevice, QSaveFile, QTimer
from qfluentwidgets import isDarkTheme

from chemunited.qt.shared.editor.lexer import ThemedLexerPython


class EditorBase(QsciScintilla):
    """
    Shared source-code editor used inside the script editor window.

    Nomenclature for the visible editor parts:

    - Editor widget: this whole QsciScintilla object. It is the large code area
      placed in the window by ScriptEditorWindow.
    - Text area: the main white/dark region where Python source text is edited.
    - Line-number gutter: margin 0, the vertical strip on the left that shows
      line numbers such as 1, 2, 3. QScintilla calls this a "margin".
    - Fold gutter: the collapse/expand margin that shows QScintilla's built-in
      fold controls for ranges such as classes, methods, and indented blocks.
    - Caret: the text cursor that marks where typing will happen.
    - Caret line: the highlighted row containing the caret.
    - Indentation guides: faint vertical guide lines that show nested blocks.
    - Lexer: the syntax highlighter that colors Python keywords, strings, and
      comments based on the active theme.
    - Autosave timer: a debounced timer that writes edits to disk shortly after
      the user stops typing.

    The surrounding window chrome, title bar, and right navigation rail belong
    to ScriptEditorWindow, not this base editor widget.
    """

    AUTOSAVE_INTERVAL_MS = 2000
    LINE_NUMBER_MARGIN_WIDTH = "000000"
    FOLD_STYLE = QsciScintilla.BoxedTreeFoldStyle

    def __init__(
        self,
        parent,
        path: Path,
    ):
        super().__init__(parent=parent)

        # Define theme palettes for light and dark modes
        name = "dark" if isDarkTheme() else "light"
        theme_json = f":/lexer_palettes/lexer/theme_{name}.json"

        # -- File Management --------------------------------

        # Internal state tracking flags
        self._current_file_changed = False
        self.first_launch = True
        # File path configuration
        self.path = path
        self.full_path = self.path.absolute()
        # Signal hooks
        self.textChanged.connect(self._textChanged)

        # Autosave timer (debounced)
        self._autosave_enabled: bool = True
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.timeout.connect(self.autosave)

        # ─── Editor Setup ─────────────────────────────────────

        # Set encoding to UTF-8
        self.setUtf8(True)

        # Enable sloppy brace matching (matches even if spacing isn't exact)
        self.setBraceMatching(QsciScintilla.SloppyBraceMatch)

        # Configure indentation and tab behavior
        self.setIndentationGuides(True)  # Show vertical indentation lines
        self.setTabWidth(4)  # Use 4 spaces per tab
        self.setIndentationsUseTabs(False)  # Use spaces instead of tab characters
        self.setAutoIndent(True)  # Auto-indent on newline

        # Customize caret (cursor) appearance
        self.setCaretLineVisible(True)  # Highlight the line with the caret
        self.setCaretWidth(2)  # Make caret thicker

        # Set end-of-line mode and visibility
        self.setEolMode(QsciScintilla.EolWindows)  # Use Windows-style line endings
        self.setEolVisibility(False)  # Hide EOL characters

        # Enable QScintilla's native collapse/expand controls for code blocks.
        self.setFolding(self.FOLD_STYLE)

        # ─── Syntax Highlighting ───────────────────────────

        self.pylexer = ThemedLexerPython(theme_path=theme_json, parent=self)
        # Apply lexer to the editor
        self.pylexer.apply_to_editor(self)

        # ─── Line Numbers ───────────────────────────────────

        self.setMarginType(0, QsciScintilla.NumberMargin)  # Enable line numbers
        self.setMarginWidth(0, self.LINE_NUMBER_MARGIN_WIDTH)  # Reserve gutter width

        # Load file content into the editor
        self._load_content()

    def _load_content(self):
        """Load the initial text content from file."""
        self.setText(self.path.read_text(encoding="utf-8"))

    def _textChanged(self):
        # Ignore the programmatic change from setText() on first launch
        if self.first_launch:
            self.first_launch = False
            return

        self._current_file_changed = True
        # Debounce: restart timer on every keystroke
        self._autosave_timer.start(self.AUTOSAVE_INTERVAL_MS)

    def set_autosave(self, enabled: bool) -> None:
        self._autosave_enabled = enabled
        if not enabled:
            self._autosave_timer.stop()

    def autosave(self):
        if not self._autosave_enabled or not self._current_file_changed:
            return
        ok, err = self._write_to_disk(self.text())
        if ok:
            self._current_file_changed = False
            # (optional) notify status bar / parent: “Saved”
            # self.parent().show_status("Saved")
        else:
            # (optional) surface the error somewhere visible
            # self.parent().show_error(f"Autosave failed: {err}")
            logger.error(f"Autosave failed: {err}")

    def save_now(self) -> bool:
        """Manual save hook if you want a menu/shortcut too."""
        ok, _ = self._write_to_disk(self.text())
        if ok:
            self._current_file_changed = False
        return ok

    def _write_to_disk(self, content: str):
        """Atomic write with QSaveFile so partial writes don't corrupt the file."""
        try:
            savefile = QSaveFile(str(self.full_path))
            if not savefile.open(
                QIODevice.WriteOnly | QIODevice.Text  # type: ignore[attr-defined]
            ):
                return False, f"Open error: {savefile.errorString()}"
            # QsciScintilla is set to UTF-8; keep encoding consistent
            savefile.write(content.encode("utf-8"))
            if not savefile.commit():
                return False, f"Commit error: {savefile.errorString()}"
            return True, ""
        except Exception as e:
            return False, str(e)

    # (nice to have) ensure last edits are flushed on close/focus change
    def closeEvent(self, e):
        self._autosave_timer.stop()
        if self._current_file_changed:
            self.autosave()
        super().closeEvent(e)


if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication
    from qfluentwidgets import Theme, setTheme

    app = QApplication(sys.argv)
    setTheme(Theme.LIGHT)
    file = Path(__file__)
    editor = EditorBase(None, file)
    editor.show()
    sys.exit(app.exec_())
