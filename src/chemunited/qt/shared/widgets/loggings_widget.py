from __future__ import annotations

from collections import deque
from datetime import datetime
from html import escape
from typing import Any

from PyQt5.QtCore import QFile, Qt, QTextStream
from PyQt5.QtGui import QTextCursor
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout
from qfluentwidgets import FluentIcon, PushButton, TextBrowser, isDarkTheme

from .segment_widget import SegmentWindow


def _read_resource_text(path: str) -> str:
    file = QFile(path)
    if not file.open(QFile.ReadOnly | QFile.Text):  # type: ignore[attr-defined]
        raise FileNotFoundError(f"Failed to open resource file: {path}")

    try:
        stream = QTextStream(file)
        return str(stream.readAll())
    finally:
        file.close()


def _loggings_widget_qss() -> str:
    color = "dark" if isDarkTheme() else "light"
    path = f":/styles/qss/{color}/loggings_widget.qss"
    return _read_resource_text(path)


def _loggings_document_css() -> str:
    if isDarkTheme():
        body_color = "#F3F4F6"
        pre_bg = "rgba(255,255,255,0.05)"
        pre_border = "rgba(255,255,255,0.10)"
        hr_color = "rgba(255,255,255,0.12)"
    else:
        body_color = "#111827"
        pre_bg = "rgba(0,0,0,0.03)"
        pre_border = "rgba(0,0,0,0.08)"
        hr_color = "rgba(0,0,0,0.12)"

    return f"""
    body {{ font-family: Segoe UI, Arial; font-size: 12px; color: {body_color}; }}
    .small {{ font-size: 11px; opacity: 0.75; }}
    .title {{ font-weight: 600; }}
    .msg   {{ margin-top: 4px; font-size: 12px; line-height: 1.35; }}
    pre {{
        white-space: pre-wrap;
        font-family: Consolas, monospace;
        font-size: 11px;
        margin: 6px 0;
        background: {pre_bg};
        padding: 8px;
        border-radius: 8px;
        border: 1px solid {pre_border};
    }}
    hr {{ border: none; border-top: 1px solid {hr_color}; margin: 10px 0; }}
    """


def _severity_styles(sev_key: str) -> dict[str, str]:
    if isDarkTheme():
        developer_bg = "rgba(255,255,255,0.04)"
        developer_border = "rgba(255,255,255,0.12)"
        meta_fg = "#D1D5DB"
        reporting = {"bg": "#1F2937", "fg": "#F9FAFB", "badge": "#6B7280"}
    else:
        developer_bg = "#FFFFFF"
        developer_border = "rgba(0,0,0,0.12)"
        meta_fg = "#4B5563"
        reporting = {"bg": "#F3F4F6", "fg": "#111827", "badge": "#6B7280"}

    styles = {
        "fatal": {"bg": "#FDECEA", "fg": "#B71C1C", "badge": "#D32F2F"},
        "error": {"bg": "#FDECEA", "fg": "#B71C1C", "badge": "#D32F2F"},
        "warning": {"bg": "#FFF4E5", "fg": "#8D6E00", "badge": "#F9A825"},
        "success": {"bg": "#E8F5E9", "fg": "#1B5E20", "badge": "#2E7D32"},
        "reporting": reporting,
    }

    resolved = styles.get(sev_key, styles["reporting"]).copy()
    resolved["developer_bg"] = developer_bg
    resolved["developer_border"] = developer_border
    resolved["meta_fg"] = meta_fg
    return resolved


class FrameLoggings(QFrame):
    """
    Two TextBrowsers:
      1) Friendly (user-facing): short, crucial info
      2) Developer (detailed): context + exception + traceback

    Styling:
      - Widget theme is loaded from a dedicated QSS resource
      - Base HTML/CSS and severity styles are handled by module helpers
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self._history: deque[dict[str, Any]] = deque(maxlen=100)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        self.clear_button = PushButton(FluentIcon.DELETE, "Clear Loggings")
        self.clear_button.clicked.connect(self._onClickedClearLoggings)
        top_bar.addStretch(1)
        top_bar.addWidget(
            self.clear_button,
            alignment=Qt.AlignHCenter,  # type: ignore[attr-defined]
        )

        root.addLayout(top_bar)

        self.main_window = SegmentWindow(self)

        self.text = TextBrowser(self)
        self.detail_loggins = TextBrowser(self)

        self.main_window.addSubInterface(
            widget=self.text,
            text="Loggings - Resume",
            objectName="text",
            icon=FluentIcon.CHAT,
        )

        self.main_window.addSubInterface(
            widget=self.detail_loggins,
            text="Detailed Records",
            objectName="detail_loggins",
            icon=FluentIcon.ROBOT,
        )

        root.addWidget(self.main_window)

        widget_qss = _loggings_widget_qss()
        self.text.setStyleSheet(widget_qss)
        self.detail_loggins.setStyleSheet(widget_qss)

        base_css = _loggings_document_css()
        self.text.document().setDefaultStyleSheet(base_css)
        self.detail_loggins.document().setDefaultStyleSheet(base_css)

    def append_record(self, r: dict):
        """
        Append a Loguru record dict (message.record) to both windows.
        """
        self._history.append(r)

        self._append_developer_record(r)

        sev_key = self._sev_key_from_record(r)
        if sev_key in {"fatal", "error", "warning", "success"}:
            self._append_friendly_record(r)

    def _sev_key_from_record(self, r: dict) -> str:
        """
        Convert Loguru level to style keys.
        """
        level = (
            str(r.get("level").name).lower()  # type: ignore[union-attr]
            if r.get("level")
            else "reporting"
        )

        mapping = {
            "trace": "reporting",
            "debug": "reporting",
            "info": "reporting",
            "success": "success",
            "warning": "warning",
            "error": "error",
            "critical": "fatal",
        }
        return mapping.get(level, "reporting")

    def _onClickedClearLoggings(self):
        self.text.clear()
        self.detail_loggins.clear()
        self._history.clear()

    def _append_html(self, tb: TextBrowser, html: str):
        sb = tb.verticalScrollBar()
        at_bottom = sb.value() >= sb.maximum() - 5

        tb.moveCursor(QTextCursor.End)
        tb.insertHtml(html)
        tb.insertPlainText("\n")

        if at_bottom:
            sb.setValue(sb.maximum())

    def _append_friendly_record(self, r: dict):
        ts = r.get("time")
        ts_str = (
            ts.strftime("%Y-%m-%d %H:%M:%S")
            if ts
            else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )

        sev_key = self._sev_key_from_record(r)
        s = _severity_styles(sev_key)

        msg = escape(str(r.get("message", "") or "")).replace("\n", "<br>")

        location = f"{r.get('name', '')}:{r.get('function', '')}:{r.get('line', '')}"
        location = escape(location)

        html = f"""
        <div style="
            margin:6px 0; padding:8px 10px; border-radius:10px;
            background:{s['bg']}; color:{s['fg']};
            border:1px solid rgba(0,0,0,0.10);
        ">
          <div style="display:flex; align-items:center; gap:8px;">
            <span style="
                display:inline-block; padding:2px 8px; border-radius:999px;
                background:{s['badge']}; color:white; font-size:11px; font-weight:600;">
              {sev_key.upper()}
            </span>
            <span class="small">{ts_str}</span>
            <span class="title">{location}</span>
          </div>

          <div class="msg">{msg}</div>
        </div>
        """
        self._append_html(self.text, html)

    def _append_developer_record(self, r: dict):
        ts = r.get("time")
        ts_str = (
            ts.strftime("%Y-%m-%d %H:%M:%S")
            if ts
            else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )

        sev_key = self._sev_key_from_record(r)
        s = _severity_styles(sev_key)

        module = str(r.get("name", "") or "")
        func = str(r.get("function", "") or "")
        line = str(r.get("line", "") or "")
        location = escape(f"{module}:{func}:{line}")

        msg = escape(str(r.get("message", "") or "")).replace("\n", "<br>")

        file_obj = r.get("file")
        file_path = escape(getattr(file_obj, "path", "") or "")
        thread_obj = r.get("thread")
        process_obj = r.get("process")

        thread_info = (
            f"{getattr(thread_obj, 'id', '')} {getattr(thread_obj, 'name', '')}".strip()
        )
        process_info = f"{getattr(process_obj, 'id', '')} {getattr(process_obj, 'name', '')}".strip()

        thread_info = escape(thread_info)
        process_info = escape(process_info)

        level_obj = r.get("level")
        level_name = escape(getattr(level_obj, "name", "") or "")
        level_no = escape(str(getattr(level_obj, "no", "") or ""))

        extra = r.get("extra", {}) or {}
        extra_repr = escape(repr(extra))

        exc = r.get("exception")
        exception_block = ""
        traceback_block = ""

        if exc is not None:
            exc_type = escape(
                getattr(exc, "type", None).__name__  # type: ignore[union-attr]
                if getattr(exc, "type", None)
                else "Exception"
            )
            exc_val = escape(str(getattr(exc, "value", "") or ""))

            exception_block = f"""
            <div class="msg"><b>Exception</b>: {exc_type} - {exc_val}</div>
            """

            tb = getattr(exc, "traceback", None)
            if tb is not None:
                tb_str = escape(str(tb))
                traceback_block = f"""
                <div class="msg"><b>Traceback</b>:</div>
                <pre>{tb_str}</pre>
                """

        separator = "<hr>" if (exception_block or traceback_block or extra) else ""

        html = f"""
        <div style="
            margin:6px 0; padding:10px; border-radius:12px;
            border:1px solid {s['developer_border']};
            background:{s['developer_bg']};
        ">
          <div style="display:flex; align-items:center; gap:8px;">
            <span style="
                display:inline-block; padding:2px 8px; border-radius:999px;
                background:{s['badge']}; color:white; font-size:11px; font-weight:600;">
              {sev_key.upper()}
            </span>
            <span class="small">{ts_str}</span>
            <span class="small">&bull; {location}</span>
          </div>

          <div class="msg">{msg}</div>

          <div class="small" style="margin-top:6px; color:{s['meta_fg']};">
            File: {file_path}<br>
            Thread: {thread_info}<br>
            Process: {process_info}<br>
            Level: {level_name} ({level_no})
          </div>

          {separator}

          <div class="msg"><b>Extra</b>:</div>
          <pre>{extra_repr}</pre>

          {exception_block}
          {traceback_block}
        </div>
        """
        self._append_html(self.detail_loggins, html)
