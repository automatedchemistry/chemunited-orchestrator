import json
from typing import Any

from PyQt5.Qsci import QsciLexerPython
from PyQt5.QtCore import QFile, QIODevice
from PyQt5.QtGui import QColor, QFont


class ThemedLexerPython(QsciLexerPython):

    TOKEN_MAP = {
        "Default": QsciLexerPython.Default,
        "Comment": QsciLexerPython.Comment,
        "CommentBlock": QsciLexerPython.CommentBlock,
        "Number": QsciLexerPython.Number,
        "DoubleQuotedString": QsciLexerPython.DoubleQuotedString,
        "SingleQuotedString": QsciLexerPython.SingleQuotedString,
        "TripleSingleQuotedString": QsciLexerPython.TripleSingleQuotedString,
        "TripleDoubleQuotedString": QsciLexerPython.TripleDoubleQuotedString,
        "Keyword": QsciLexerPython.Keyword,
        "HighlightedIdentifier": QsciLexerPython.HighlightedIdentifier,
        "Operator": QsciLexerPython.Operator,
        "Identifier": QsciLexerPython.Identifier,
        "FunctionMethodName": QsciLexerPython.FunctionMethodName,
        "ClassName": QsciLexerPython.ClassName,
        "Decorator": QsciLexerPython.Decorator,
    }

    def __init__(self, theme_path: str, parent=None):
        super().__init__(parent)
        self._colors: dict[int, QColor] = {}
        self._papers: dict[int, QColor] = {}
        self._fonts: dict[int, QFont] = {}
        self._load_theme(theme_path)

    def _load_theme(self, path: str) -> None:
        file = QFile(path)
        if not file.open(QIODevice.ReadOnly | QIODevice.Text):
            return
        data: dict[str, Any] = json.loads(bytes(file.readAll()).decode("utf-8"))
        file.close()

        # --- editor-level settings stored as attributes ---
        self.editor_foreground = QColor(data.get("ForegroundColor", "#000000"))
        self.editor_background = QColor(data.get("BackgroundColor", "#ffffff"))
        self.editor_paper = QColor(data.get("Paper", "#ffffff"))
        self.editor_color = QColor(data.get("Color", "#000000"))
        self.editor_margins_fg = QColor(data.get("MarginsForegroundColor", "#888888"))
        self.editor_margins_bg = QColor(data.get("MarginsBackgroundColor", "#ffffff"))
        self.editor_font_size = data.get("FontSize", 10)

        # --- token-level settings (same as before) ---
        default_font_family = data.get("font_family", "Monospace")
        default_font_size = self.editor_font_size

        for token_name, style_id in self.TOKEN_MAP.items():
            token_data = data.get("tokens", {}).get(token_name, {})

            fg = token_data.get("color")
            bg = token_data.get("paper", data.get("Paper", "#ffffff"))
            bold = token_data.get("bold", False)
            italic = token_data.get("italic", False)

            font = QFont(default_font_family, default_font_size)
            font.setBold(bold)
            font.setItalic(italic)
            fg_color = QColor(fg or data.get("Color", "#000000"))
            bg_color = QColor(bg)

            self._colors[style_id] = fg_color
            self._papers[style_id] = bg_color
            self._fonts[style_id] = font

            # Use setters directly instead of relying on default* overrides
            self.setColor(fg_color, style_id)
            self.setPaper(bg_color, style_id)
            self.setFont(font, style_id)

    def apply_to_editor(self, editor) -> None:
        editor.setLexer(self)

        # Force the lexer defaults to propagate to the editor
        self.setDefaultColor(self.editor_color)
        self.setDefaultPaper(self.editor_paper)

        # This is the key call - it reapplies all default* values
        self.setFont(self.defaultFont(self.Default))
        editor.setMarginsFont(self.defaultFont(self.Default))

        editor.setPaper(self.editor_paper)
        editor.setColor(self.editor_color)
        editor.setMarginsBackgroundColor(self.editor_margins_bg)
        editor.setMarginsForegroundColor(self.editor_margins_fg)
        editor.setCaretForegroundColor(self.editor_foreground)
        editor.setCaretLineBackgroundColor(self.editor_background)

    def defaultColor(self, style: int) -> QColor:
        return self._colors.get(style, QColor("#000000"))

    def defaultPaper(self, style: int) -> QColor:
        return self._papers.get(style, QColor("#ffffff"))

    def defaultFont(self, style: int) -> QFont:
        return self._fonts.get(style, QFont("Monospace", 10))
