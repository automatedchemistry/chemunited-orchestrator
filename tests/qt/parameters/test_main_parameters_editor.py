from __future__ import annotations

from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from chemunited.shared.editor.parameters.main import MainParametersEditor
from chemunited.shared.widgets.base_mode_editor.cards.builder_models import (
    StringVariableBuildMode,
)

SOURCE = """from pydantic import BaseModel, Field


def helper():
    return "helper"


class ProcessParameters(BaseModel):
    run_label: str = Field(
        default="run-01",
        title="Run Label",
        description="Short run name.",
        min_length=3,
        max_length=20,
        json_schema_extra={"group": "General", "editable": True, "visible": True},
    )

    cycles: int = Field(
        default=2,
        title="Cycles",
        description="Number of cycles.",
        ge=1,
        le=9,
        json_schema_extra={"group": "General", "editable": True, "visible": True},
    )

    def update(self):
        ...


class Tail:
    value = 1
"""


@pytest.fixture
def parameters_file(tmp_path: Path) -> Path:
    path = tmp_path / "parameters.py"
    path.write_text(SOURCE, encoding="utf-8")
    return path


def _make_window(path: Path, qtbot: QtBot) -> MainParametersEditor:
    window = MainParametersEditor(path=path, class_name="ProcessParameters")
    qtbot.addWidget(window)
    return window


def test_startup_does_not_modify_file(parameters_file: Path, qtbot: QtBot) -> None:
    original = parameters_file.read_text(encoding="utf-8")

    window = _make_window(parameters_file, qtbot)

    assert parameters_file.read_text(encoding="utf-8") == original
    assert len(window.param_list._cards) == 2
    assert not hasattr(window, "editor")
    assert not hasattr(window, "pivot")


def test_valid_edits_write_and_invalid_edits_do_not_write(
    parameters_file: Path,
    qtbot: QtBot,
) -> None:
    window = _make_window(parameters_file, qtbot)
    card = window.param_list._cards[0]

    default_editor = card._editors["default"]
    default_editor.setText("run-02")
    qtbot.waitUntil(
        lambda: 'default="run-02"' in parameters_file.read_text(encoding="utf-8")
    )

    updated = parameters_file.read_text(encoding="utf-8")
    assert "def helper():" in updated
    assert "def update(self):" in updated
    assert "class Tail:" in updated

    name_editor = card._editors["name"]
    name_editor.setText("1bad")
    qtbot.wait(50)

    assert parameters_file.read_text(encoding="utf-8") == updated
    assert not card.validate()


def test_add_duplicate_and_delete_write_immediately(
    parameters_file: Path,
    qtbot: QtBot,
) -> None:
    window = _make_window(parameters_file, qtbot)

    assert parameters_file.read_text(encoding="utf-8").count(" = Field(") == 2

    window._add_card(StringVariableBuildMode())
    qtbot.waitUntil(
        lambda: parameters_file.read_text(encoding="utf-8").count(" = Field(") == 3
    )

    first_card = window.param_list._cards[0]
    first_card.duplicate.emit(first_card)
    qtbot.waitUntil(
        lambda: parameters_file.read_text(encoding="utf-8").count(" = Field(") == 4
    )

    last_card = window.param_list._cards[-1]
    last_card.deleted.emit(last_card)
    qtbot.waitUntil(
        lambda: parameters_file.read_text(encoding="utf-8").count(" = Field(") == 3
    )
