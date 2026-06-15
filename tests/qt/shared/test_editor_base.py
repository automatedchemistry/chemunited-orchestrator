from pathlib import Path

from pytestqt.qtbot import QtBot

from chemunited.shared.editor.base import EditorBase


def test_editor_base_enables_native_qscintilla_folding(
    tmp_path: Path,
    qtbot: QtBot,
) -> None:
    path = tmp_path / "script.py"
    path.write_text(
        "class Process:\n" "    def check_pressure(self):\n" "        return True\n",
        encoding="utf-8",
    )

    editor = EditorBase(parent=None, path=path)
    qtbot.addWidget(editor)

    assert editor.folding() == editor.FOLD_STYLE
