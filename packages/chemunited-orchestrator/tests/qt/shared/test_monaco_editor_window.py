"""Window-level pytest tests for ``MonacoProcessScriptEditorWindow`` (tabs).

Adapted from the standalone script ``window_test_monaco.py`` that used to
live in the package root. Covers the tabbed IDE behavior: opening a second
file as a tab, per-file text isolation, JS-side tab switching, the
"never close the last tab" guard, no sidebar, and the ``focus_method``
race (called before the Monaco page is ready must be replayed on ready).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from chemunited.protocols.workflows.monaco_editor import (
    MonacoProcessScriptEditorWindow,
)

# Each process script carries a "<ClassName>Config" pydantic class so the
# ParameterDragableList dock can load it without logging an import error.
ALPHA_SOURCE = """from pydantic import BaseModel


class AlphaProcessConfig(BaseModel):
    pass


class AlphaProcess:
    def __init__(self):
        self.n = 0

    def run(self):
        print("alpha")
        return True

    def cleanup(self):
        pass
"""

BETA_SOURCE = """from pydantic import BaseModel


class BetaProcessConfig(BaseModel):
    pass


class BetaProcess:
    def __init__(self):
        self.n = 0

    def run(self):
        print("beta")
        return False
"""


def _run_js(page, expr: str, qtbot, timeout_ms: int = 10000):
    """Run a JS expression in the page and wait for its callback value."""
    result: dict = {}
    page.runJavaScript(expr, lambda value: result.update(value=value))
    qtbot.waitUntil(lambda: "value" in result, timeout=timeout_ms)
    return result["value"]


def _expected_cursor(source: str, statement: str) -> tuple[int, int]:
    """0-based (line, col) of a method body statement, as focus_method does."""
    lines = source.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.startswith(statement):
            return index, len(line) - len(line.lstrip(" "))
    raise AssertionError(f"statement not found in source: {statement!r}")


@pytest.fixture
def script_a(tmp_path: Path) -> Path:
    path = tmp_path / "protocols" / "alpha.py"
    path.parent.mkdir()
    path.write_text(ALPHA_SOURCE, encoding="utf-8")
    return path


@pytest.fixture
def script_b(tmp_path: Path) -> Path:
    path = tmp_path / "protocols" / "beta.py"
    path.parent.mkdir(exist_ok=True)
    path.write_text(BETA_SOURCE, encoding="utf-8")
    return path


@pytest.fixture
def window(qtbot, script_a: Path, script_b: Path) -> MonacoProcessScriptEditorWindow:
    win = MonacoProcessScriptEditorWindow(path=script_a, class_name="AlphaProcess")
    qtbot.addWidget(win)
    win.show()
    return win


def _await_ready(win, qtbot) -> None:
    qtbot.waitUntil(lambda: getattr(win.editor, "_editor_ready", False), timeout=30000)
    # focus_method's cursor _apply runs ~100 ms after ready; let it land.
    qtbot.wait(400)


def test_no_sidebar_and_initial_file(
    qtbot, window: MonacoProcessScriptEditorWindow
) -> None:
    """The editor opens with the initial file and has no file-tree sidebar."""
    _await_ready(window, qtbot)
    page = window.editor.web_view.page()
    assert "class AlphaProcess" in window.editor.text()
    assert not _run_js(page, "!!document.getElementById('sidebar')", qtbot)


def test_open_second_file_creates_tab(
    qtbot, window: MonacoProcessScriptEditorWindow, script_b: Path
) -> None:
    """``open_file`` on a script opens it as a second tab and activates it."""
    _await_ready(window, qtbot)
    page = window.editor.web_view.page()

    window.open_file(script_b, class_name="BetaProcess")
    qtbot.wait(500)

    assert window.editor.path == script_b
    assert "class BetaProcess" in window.editor.text()
    assert _run_js(page, "monacoEditor.listOpenFiles().length", qtbot) == 2
    assert _run_js(page, "monacoEditor.getFilePath()", qtbot).endswith("beta.py")


def test_editing_one_tab_leaves_other_intact(
    qtbot,
    window: MonacoProcessScriptEditorWindow,
    script_a: Path,
    script_b: Path,
) -> None:
    """Per-tab models are isolated: editing alpha must not touch beta."""
    _await_ready(window, qtbot)
    page = window.editor.web_view.page()

    window.open_file(script_b, class_name="BetaProcess")
    qtbot.wait(500)
    # Switch back to alpha before editing, as the app does when the user
    # returns to the first tab.
    window.editor.open_file(script_a)
    qtbot.wait(500)
    window.editor.setText("# alpha edited\n")
    qtbot.wait(500)

    beta_text = _run_js(
        page,
        "(function () {"
        "    const models = monaco.editor.getModels();"
        "    const beta = models.find("
        "        m => m.uri.toString().indexOf('beta') !== -1);"
        "    return beta ? beta.getValue() : 'MISSING';"
        "})()",
        qtbot,
    )
    assert "class BetaProcess" in beta_text


def test_js_tab_click_switches_active_file(
    qtbot, window: MonacoProcessScriptEditorWindow, script_b: Path
) -> None:
    """Clicking a tab in JS syncs the active path, cache, and title."""
    _await_ready(window, qtbot)
    page = window.editor.web_view.page()

    window.open_file(script_b, class_name="BetaProcess")
    qtbot.wait(500)

    _run_js(
        page,
        "(function () {"
        "    const tab = Array.from(document.querySelectorAll('.tab'))"
        "        .find(t => t.dataset.path && t.dataset.path.indexOf('beta') !== -1);"
        "    if (tab) tab.click();"
        "})()",
        qtbot,
    )
    qtbot.wait(500)

    assert window.editor.path == script_b
    assert "class BetaProcess" in window.editor.text()
    assert "beta.py" in window.windowTitle()


def test_last_tab_cannot_be_closed(
    qtbot, window: MonacoProcessScriptEditorWindow, script_b: Path
) -> None:
    """Closing every tab leaves exactly one tab open."""
    _await_ready(window, qtbot)
    page = window.editor.web_view.page()

    window.open_file(script_b, class_name="BetaProcess")
    qtbot.wait(500)

    _run_js(
        page,
        "(function () {"
        "    const tabs = Array.from(document.querySelectorAll('.tab'));"
        "    for (const t of tabs) {"
        "        const close = t.querySelector('.close');"
        "        if (close) close.click();"
        "    }"
        "})()",
        qtbot,
    )
    qtbot.wait(500)

    remaining = _run_js(page, "monacoEditor.listOpenFiles().length", qtbot)
    assert remaining == 1


def test_focus_method_before_ready_is_replayed(
    qtbot, window: MonacoProcessScriptEditorWindow
) -> None:
    """focus_method called on a not-yet-loaded page is deferred and re-run."""
    # Race the editor: the Monaco page has not loaded yet.
    assert not getattr(window.editor, "_editor_ready", False)
    window.focus_method("run")

    _await_ready(window, qtbot)

    expected = _expected_cursor(ALPHA_SOURCE, "        print(")
    assert window._current_focused_method == "run"
    assert window.editor.getCursorPosition() == expected
