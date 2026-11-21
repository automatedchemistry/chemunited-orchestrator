from __future__ import annotations

from pathlib import Path

from pytestqt.qtbot import QtBot

from chemunited.shared.editor.parameters.drag_list import ParameterDragableList


def test_lists_the_fields_of_a_process_that_uses_relative_imports(
    process_with_relative_imports: Path,
    qtbot: QtBot,
) -> None:
    widget = ParameterDragableList(
        path=process_with_relative_imports, class_name="ProcessConfig"
    )
    qtbot.addWidget(widget)

    fields = [widget._list.item(row).text() for row in range(widget._list.count())]
    assert fields == ["cycles"]
