from pathlib import Path

from PyQt5.Qsci import QsciScintilla
from pytestqt.qtbot import QtBot

from chemunited.qt.protocols.workflows.editor import ProcessScriptEditorWindow

SOURCE = """\
class CustomProcess:
    def enter(self, ctx):
        return True

    def check_pressure(self, ctx):
        self._pause(ctx)
        ctx.runtime.local_data["primary_route"] = self.config.primary_route
        return self.config.primary_route

    def handle_low_pressure(self, ctx):
        self._pause(ctx)
        return True
"""


def _make_window(tmp_path: Path, qtbot: QtBot) -> ProcessScriptEditorWindow:
    path = tmp_path / "process.py"
    path.write_text(SOURCE, encoding="utf-8")
    window = ProcessScriptEditorWindow(path=path, class_name="CustomProcess")
    qtbot.addWidget(window)
    return window


def _line_index(text: str, needle: str) -> int:
    return next(index for index, line in enumerate(text.splitlines()) if needle in line)


def _marker_mask(window: ProcessScriptEditorWindow) -> int:
    return 1 << window.editor._FOCUS_MARKER


def _has_focus_marker(window: ProcessScriptEditorWindow, line: int) -> bool:
    return bool(window.editor.markersAtLine(line) & _marker_mask(window))


def _indicator_mask_at_line(window: ProcessScriptEditorWindow, line: int) -> int:
    pos = window.editor.SendScintilla(QsciScintilla.SCI_POSITIONFROMLINE, line)
    return window.editor.SendScintilla(QsciScintilla.SCI_INDICATORALLONFOR, pos)


def test_focus_method_marks_body_lines_not_signature(
    tmp_path: Path,
    qtbot: QtBot,
) -> None:
    window = _make_window(tmp_path, qtbot)

    window.focus_method("check_pressure")

    signature = _line_index(SOURCE, "def check_pressure")
    body_start = _line_index(SOURCE, "self._pause(ctx)")
    body_end = _line_index(SOURCE, "return self.config.primary_route")

    assert window.editor._protected
    assert window.editor._body_start == body_start
    assert window.editor._body_end == body_end
    assert not _has_focus_marker(window, signature)
    for line in range(body_start, body_end + 1):
        assert _has_focus_marker(window, line)

    window.close()


def test_clear_protected_zone_removes_focus_markers_and_dim_overlay(
    tmp_path: Path,
    qtbot: QtBot,
) -> None:
    window = _make_window(tmp_path, qtbot)

    window.focus_method("check_pressure")
    body_start = window.editor._body_start

    assert _has_focus_marker(window, body_start)
    assert _indicator_mask_at_line(window, 0) != 0

    window.editor.clear_protected_zone()

    assert not _has_focus_marker(window, body_start)
    assert _indicator_mask_at_line(window, 0) == 0

    window.close()


def test_focus_markers_follow_inserted_body_lines(
    tmp_path: Path,
    qtbot: QtBot,
) -> None:
    window = _make_window(tmp_path, qtbot)
    window.focus_method("check_pressure")

    old_body_end = window.editor._body_end
    window.editor.insertAt("        inserted = True\n", old_body_end, 0)
    qtbot.wait(0)

    assert window.editor._body_end == old_body_end + 1
    for line in range(window.editor._body_start, window.editor._body_end + 1):
        assert _has_focus_marker(window, line)

    window.close()
