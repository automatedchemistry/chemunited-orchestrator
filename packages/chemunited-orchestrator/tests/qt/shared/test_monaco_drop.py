"""Dragging commands and parameters into the Monaco script editor."""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt5.QtCore import QMimeData, QPoint, Qt
from PyQt5.QtGui import QDragEnterEvent, QDropEvent
from PyQt5.QtWidgets import QApplication

from chemunited.protocols.workflows.monaco_editor import (
    MonacoProcessScriptEditorWindow,
)
from chemunited.shared.editor.parameters.drag_list import ParameterDragableList
from chemunited.shared.editor.protocols.command_list import CommandList

SOURCE = """from pydantic import BaseModel


class AlphaProcessConfig(BaseModel):
    pass


class AlphaProcess:
    def __init__(self):
        self.n = 0

    def run(self):
        print("alpha")
        return True
"""

COMMAND = 'self.platform["P1"].stop()'


def _run_js(page, expr: str, qtbot, timeout_ms: int = 10000):
    result: dict = {}
    page.runJavaScript(expr, lambda value: result.update(value=value))
    qtbot.waitUntil(lambda: "value" in result, timeout=timeout_ms)
    return result["value"]


@pytest.fixture
def window(qtbot, tmp_path: Path) -> MonacoProcessScriptEditorWindow:
    path = tmp_path / "protocols" / "alpha.py"
    path.parent.mkdir()
    path.write_text(SOURCE, encoding="utf-8")
    win = MonacoProcessScriptEditorWindow(path=path, class_name="AlphaProcess")
    qtbot.addWidget(win)
    win.resize(900, 700)
    win.show()
    qtbot.waitUntil(lambda: win.editor._editor_ready, timeout=30000)
    win.focus_method("run")
    page = win.editor.web_view.page()
    qtbot.waitUntil(
        lambda: _run_js(page, "monacoEditor.getEditableRange()", qtbot) is not None
    )
    qtbot.wait(300)
    return win


def _point_on_line(window, line_number: int, qtbot) -> QPoint:
    """View-relative point over a 1-based line of the editor."""
    pos = _run_js(
        window.editor.web_view.page(),
        "(() => { const p = editor.getScrolledVisiblePosition("
        f"{{lineNumber: {line_number}, column: 5}});"
        " const r = editor.getDomNode().getBoundingClientRect();"
        " return {x: r.left + p.left + 2, y: r.top + p.top + 2}; })()",
        qtbot,
    )
    return QPoint(int(pos["x"]), int(pos["y"]))


def _drop(window, mime: QMimeData, point: QPoint) -> None:
    """Deliver a drag like Qt does: enter on the widget under the cursor
    (the web view's render child), then drop on the accepted target."""
    view = window.editor.web_view
    target = view.childAt(point) or view
    args = (point, Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)  # type: ignore[attr-defined]
    enter = QDragEnterEvent(*args)
    QApplication.sendEvent(target, enter)
    assert enter.isAccepted()
    QApplication.sendEvent(target, QDropEvent(*args))


def _command_mime() -> QMimeData:
    mime = QMimeData()
    mime.setData(CommandList.MIME, COMMAND.encode("utf-8"))
    mime.setText(f"\n        {COMMAND}")
    return mime


def _parameter_mime(source: Path) -> QMimeData:
    mime = QMimeData()
    mime.setData(ParameterDragableList.MIME, b"self.config.speed")
    mime.setData(ParameterDragableList.PATH_MIME, str(source).encode("utf-8"))
    mime.setText("self.config.speed")
    return mime


def test_command_drop_inserts_before_return(
    qtbot, window: MonacoProcessScriptEditorWindow
) -> None:
    with qtbot.waitSignal(window.editor.drop_accepted, timeout=5000):
        _drop(window, _command_mime(), _point_on_line(window, 13, qtbot))

    qtbot.waitUntil(lambda: COMMAND in window.editor.text())
    assert (
        f'        print("alpha")\n        {COMMAND}\n        return True\n'
        in window.editor.text()
    )


def test_parameter_drop_does_not_run_black(
    qtbot, window: MonacoProcessScriptEditorWindow
) -> None:
    with qtbot.assertNotEmitted(window.editor.drop_accepted, wait=500):
        _drop(
            window,
            _parameter_mime(window.editor.path),
            _point_on_line(window, 13, qtbot),
        )

    qtbot.waitUntil(lambda: "        self.config.speed\n" in window.editor.text())


def test_parameter_from_another_file_is_ignored(
    qtbot, window: MonacoProcessScriptEditorWindow, tmp_path: Path
) -> None:
    _drop(
        window,
        _parameter_mime(tmp_path / "other.py"),
        _point_on_line(window, 13, qtbot),
    )
    qtbot.wait(500)
    assert window.editor.text() == SOURCE


def test_drop_on_a_locked_line_is_ignored(
    qtbot, window: MonacoProcessScriptEditorWindow
) -> None:
    # line 10 is `self.n = 0` inside __init__, outside the run() lock
    _drop(window, _command_mime(), _point_on_line(window, 10, qtbot))
    qtbot.wait(500)
    assert window.editor.text() == SOURCE
