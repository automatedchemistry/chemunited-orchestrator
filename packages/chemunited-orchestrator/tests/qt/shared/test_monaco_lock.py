"""Method lock in the Monaco script editor (``focus_method`` / protected zone)."""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt5.QtTest import QTest

from chemunited.protocols.workflows.monaco_editor import (
    MonacoProcessScriptEditorWindow,
)

SOURCE = """from pydantic import BaseModel


class AlphaProcessConfig(BaseModel):
    pass


class AlphaProcess:
    def __init__(self):
        self.n = 0

    @staticmethod
    def helper():
        return 1

    def run(self):
        print("alpha")
        x = 1
        return True

    def cleanup(self):
        pass
"""

# 1-based lines of run()'s body in SOURCE: print(...) .. return True
RUN_BODY = {"start": 17, "end": 19}


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
    win.show()
    qtbot.waitUntil(lambda: win.editor._editor_ready, timeout=30000)
    return win


@pytest.fixture
def locked(qtbot, window: MonacoProcessScriptEditorWindow):
    window.focus_method("run")
    page = window.editor.web_view.page()
    qtbot.waitUntil(
        lambda: _run_js(page, "monacoEditor.getEditableRange()", qtbot) is not None
    )
    qtbot.wait(300)  # let focus_method's deferred cursor move land
    return window


def _model_text(window, qtbot) -> str:
    return _run_js(window.editor.web_view.page(), "editor.getValue()", qtbot)


def test_method_body_range(qtbot, window: MonacoProcessScriptEditorWindow) -> None:
    # 0-based (body_start, body_end, cursor_line, cursor_col)
    assert window._method_body_range("run") == (16, 18, 16, 8)
    # decorators and the def line stay locked: the body is just `return 1`
    assert window._method_body_range("helper") == (13, 13, 13, 8)
    assert window._method_body_range("missing", log_errors=False) is None


def test_focus_method_locks_the_body(
    qtbot, locked: MonacoProcessScriptEditorWindow
) -> None:
    page = locked.editor.web_view.page()
    assert locked.editor._protected
    assert _run_js(page, "monacoEditor.getEditableRange()", qtbot) == RUN_BODY
    dimmed = _run_js(
        page,
        "editor.getModel().getAllDecorations()"
        ".filter(d => d.options.className === 'cu-locked-line').length",
        qtbot,
    )
    assert dimmed == 2  # lines above and below the body


def test_edit_outside_the_body_is_reverted(
    qtbot, locked: MonacoProcessScriptEditorWindow
) -> None:
    page = locked.editor.web_view.page()
    # A non-keyboard edit (like a context-menu paste) on the __init__ line.
    _run_js(
        page,
        "editor.executeEdits('test', [{range: new monaco.Range(10, 1, 10, 1),"
        " text: '# outside\\n'}]); true",
        qtbot,
    )
    qtbot.waitUntil(lambda: "# outside" not in _model_text(locked, qtbot))
    assert _model_text(locked, qtbot) == SOURCE
    assert "# outside" not in locked.editor.text()
    assert _run_js(page, "monacoEditor.getEditableRange()", qtbot) == RUN_BODY


def test_edit_inside_the_body_grows_the_zone(
    qtbot, locked: MonacoProcessScriptEditorWindow
) -> None:
    page = locked.editor.web_view.page()
    _run_js(
        page,
        "editor.executeEdits('test', [{range: new monaco.Range(18, 1, 18, 1),"
        " text: '        y = 2\\n'}]); true",
        qtbot,
    )
    qtbot.wait(200)
    assert "        y = 2\n" in _model_text(locked, qtbot)
    assert "        y = 2\n" in locked.editor.text()
    assert _run_js(page, "monacoEditor.getEditableRange()", qtbot) == {
        "start": 17,
        "end": 20,
    }


def test_typing_is_blocked_on_locked_lines(
    qtbot, locked: MonacoProcessScriptEditorWindow
) -> None:
    page = locked.editor.web_view.page()
    target = locked.editor.web_view.focusProxy() or locked.editor.web_view

    # caret on the `def run` line (locked)
    _run_js(page, "editor.setPosition({lineNumber: 16, column: 5}); true", qtbot)
    locked.editor.focus()
    QTest.keyClicks(target, "zz")
    qtbot.wait(300)
    assert _model_text(locked, qtbot) == SOURCE

    # caret inside the body
    _run_js(page, "editor.setPosition({lineNumber: 18, column: 9}); true", qtbot)
    locked.editor.focus()
    QTest.keyClicks(target, "zz")
    qtbot.waitUntil(lambda: "zzx = 1" in _model_text(locked, qtbot))


def test_insert_at_respects_the_lock(
    qtbot, locked: MonacoProcessScriptEditorWindow
) -> None:
    page = locked.editor.web_view.page()

    locked.editor.insertAt("# blocked\n", 0, 0)
    qtbot.wait(300)
    assert "# blocked" not in _model_text(locked, qtbot)
    qtbot.waitUntil(lambda: "# blocked" not in locked.editor.text())

    # The drop rule's "after the last statement" position is the line right
    # below the zone; it is appended inside the zone instead.
    _run_js(page, "monacoEditor.clearEditableRange(); true", qtbot)
    locked.editor.set_protected_zone(16, 17)  # print(...) and x = 1 only
    locked.editor.insertAt("        y = 2\n", 18, 0)
    qtbot.waitUntil(lambda: "        y = 2\n" in _model_text(locked, qtbot))
    assert _run_js(page, "monacoEditor.getEditableRange()", qtbot) == {
        "start": 17,
        "end": 19,
    }


def test_set_text_relocks_the_method(
    qtbot, locked: MonacoProcessScriptEditorWindow
) -> None:
    page = locked.editor.web_view.page()
    locked.editor.setText("# header\n" + SOURCE)
    qtbot.waitUntil(
        lambda: _run_js(page, "monacoEditor.getEditableRange()", qtbot)
        == {"start": 18, "end": 20}
    )
    assert locked.editor._protected


def test_clear_protected_zone(qtbot, locked: MonacoProcessScriptEditorWindow) -> None:
    page = locked.editor.web_view.page()
    locked.editor.clear_protected_zone()
    qtbot.waitUntil(
        lambda: _run_js(page, "monacoEditor.getEditableRange()", qtbot) is None
    )
    assert not locked.editor._protected
