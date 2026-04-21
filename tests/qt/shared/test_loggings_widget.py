from datetime import datetime
from types import SimpleNamespace

from pytestqt.qtbot import QtBot

from chemunited.qt.shared.widgets.loggings_widget import FrameLoggings


def test_detailed_loggings_render_formatted_traceback(qtbot: QtBot):
    widget = FrameLoggings()
    qtbot.addWidget(widget)

    try:
        raise ValueError("invalid manifest")
    except Exception as exc:
        record = {
            "time": datetime.now(),
            "name": "test.module",
            "function": "test_function",
            "line": 42,
            "message": "Could not open project 'demo.chemunited': invalid manifest",
            "file": SimpleNamespace(path="demo.py"),
            "thread": SimpleNamespace(id=1, name="MainThread"),
            "process": SimpleNamespace(id=1, name="MainProcess"),
            "level": SimpleNamespace(name="ERROR", no=40),
            "extra": {"window": "setup"},
            "exception": SimpleNamespace(
                type=type(exc),
                value=exc,
                traceback=exc.__traceback__,
            ),
        }

    widget.append_record(record)

    detailed_text = widget.detail_loggins.toPlainText()
    assert "Traceback (most recent call last):" in detailed_text
    assert "ValueError: invalid manifest" in detailed_text
    assert "<traceback object" not in detailed_text
