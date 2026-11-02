"""Pytest smoke tests for the Monaco editor's QWebEngine bridge.

Adapted from the standalone scripts ``smoke_monaco.py`` /
``window_test_monaco.py`` that used to live in the package root; these
versions run under pytest-qt and follow the conventions of the other Qt
tests (see ``tests/qt/conftest.py`` for the QtWebEngine import order).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from chemunited.shared.editor.monaco_base import MonacoEditorBase

if TYPE_CHECKING:
    from PyQt5.QtWebEnginePage import QWebEnginePage  # noqa: F401


def _run_js(page, expr: str, qtbot, timeout_ms: int = 10000):
    """Run a JS expression in the page and wait for its callback value."""
    result: dict = {}
    page.runJavaScript(expr, lambda value: result.update(value=value))
    qtbot.waitUntil(lambda: "value" in result, timeout=timeout_ms)
    return result["value"]


@pytest.fixture
def sample_file(tmp_path: Path) -> Path:
    path = tmp_path / "sample.py"
    path.write_text("print('hello monaco')\n", encoding="utf-8")
    return path


@pytest.fixture
def editor(qtbot, sample_file: Path) -> MonacoEditorBase:
    editor = MonacoEditorBase(None, sample_file)
    qtbot.addWidget(editor)
    editor.show()
    qtbot.waitUntil(lambda: getattr(editor, "_editor_ready", False), timeout=30000)
    return editor


def test_js_bridges_load(qtbot, editor: MonacoEditorBase) -> None:
    """Monaco global, the editor API, and the QWebChannel pybridge all appear."""
    page = editor.web_view.page()
    assert _run_js(page, "typeof monaco !== 'undefined'", qtbot)
    assert _run_js(
        page,
        "typeof monacoEditor !== 'undefined' && !!monacoEditor.getText",
        qtbot,
    )
    assert _run_js(
        page,
        "!!(window.pybridge && window.pybridge.onTextChanged)",
        qtbot,
    )


def test_initial_file_content_is_shown(qtbot, editor: MonacoEditorBase) -> None:
    """The file's initial text is visible in JS and cached in Python."""
    page = editor.web_view.page()
    assert "hello monaco" in _run_js(page, "monacoEditor.getText()", qtbot)
    assert "hello monaco" in editor.text()


def test_js_edit_updates_python_cache(qtbot, editor: MonacoEditorBase) -> None:
    """Edits typed by JS (i.e. by the user) propagate to the Python cache."""
    page = editor.web_view.page()
    _run_js(page, "monacoEditor.insertAt('# edited\\n', 0, 0)", qtbot)
    qtbot.waitUntil(lambda: "# edited" in editor.text(), timeout=5000)


def test_python_settext_updates_js(qtbot, editor: MonacoEditorBase) -> None:
    """``setText`` from Python propagates into the Monaco model."""
    editor.setText("print('from python')\n")
    qtbot.wait(700)
    text = _run_js(editor.web_view.page(), "monacoEditor.getText()", qtbot)
    assert "from python" in text


def test_save_round_trip(qtbot, editor: MonacoEditorBase, sample_file: Path) -> None:
    """``save_now`` writes the editor content to disk."""
    editor.setText("print('saved content')\n")
    assert editor.save_now()
    qtbot.wait(300)
    assert "saved content" in sample_file.read_text(encoding="utf-8")


def test_theme_call_is_a_no_op(qtbot, editor: MonacoEditorBase) -> None:
    """Switching the editor theme must not raise or stall the bridge."""
    editor._set_theme("dark")
    qtbot.wait(300)
    assert _run_js(editor.web_view.page(), "monacoEditor.getText()", qtbot)
