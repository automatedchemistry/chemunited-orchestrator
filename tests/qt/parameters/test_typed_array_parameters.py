from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel, Field, ValidationError
from pytestqt.qtbot import QtBot

from chemunited.shared.editor.parameters.cards import generate_field_code
from chemunited.shared.editor.parameters.main import (
    MainParametersEditor,
    field_info_to_build_mode,
)
from chemunited.shared.widgets.base_mode_editor.card_factory import CardFactory
from chemunited.shared.widgets.base_mode_editor.cards.builder_models import (
    ListVariableBuildMode,
)
from chemunited.shared.widgets.base_mode_editor.cards.list_card import ListFieldCard


@pytest.mark.parametrize("element_type", ["str", "int", "float"])
def test_array_code_generation_uses_typed_annotations(element_type: str) -> None:
    defaults = {
        "str": ["A", "B"],
        "int": [1, 2],
        "float": [1, 2.5],
    }
    mode = ListVariableBuildMode(
        name="values",
        element_type=element_type,
        default=defaults[element_type],
        min_length=1,
        max_length=5,
    )

    code = generate_field_code(mode)

    assert f"values: list[{element_type}] = Field(" in code
    assert "min_length=1," in code
    assert "max_length=5," in code
    assert "min_items" not in code
    assert "max_items" not in code


def test_array_defaults_are_coerced_and_invalid_items_are_rejected() -> None:
    mode = ListVariableBuildMode(
        element_type="int",
        default=["1", 2.0],
    )

    assert mode.default == [1, 2]

    with pytest.raises(ValidationError, match="not a valid int"):
        ListVariableBuildMode(element_type="int", default=[1.5])


class TypedArrays(BaseModel):
    names: list[str] = Field(default=["A", "B"], min_length=1, max_length=4)
    counts: list[int] = Field(default=[1, 2])
    values: list[float] = Field(default=[1, 2.5])


@pytest.mark.parametrize(
    ("field_name", "element_type", "default"),
    [
        ("names", "str", ["A", "B"]),
        ("counts", "int", [1, 2]),
        ("values", "float", [1.0, 2.5]),
    ],
)
def test_loading_typed_arrays_restores_item_type(
    field_name: str,
    element_type: str,
    default: list,
) -> None:
    mode = field_info_to_build_mode(field_name, TypedArrays.model_fields[field_name])

    assert isinstance(mode, ListVariableBuildMode)
    assert mode.element_type == element_type
    assert mode.default == default

    if field_name == "names":
        assert mode.min_length == 1
        assert mode.max_length == 4


@pytest.mark.parametrize(
    ("default", "element_type", "normalized"),
    [
        (["A", "B"], "str", ["A", "B"]),
        ([1, 2], "int", [1, 2]),
        ([1, 2.5], "float", [1.0, 2.5]),
        ([], "str", []),
        ([True, 1], "str", ["True", "1"]),
        ([1, "A"], "str", ["1", "A"]),
    ],
)
def test_legacy_bare_arrays_infer_item_type(
    default: list,
    element_type: str,
    normalized: list,
) -> None:
    class LegacyArray(BaseModel):
        values: list = Field(default=default)

    mode = field_info_to_build_mode("values", LegacyArray.model_fields["values"])

    assert isinstance(mode, ListVariableBuildMode)
    assert mode.element_type == element_type
    assert mode.default == normalized


def test_runtime_factory_uses_list_card_for_bare_and_typed_lists(
    qtbot: QtBot,
) -> None:
    class RuntimeArrays(BaseModel):
        bare: list = Field(default=[1, 2], max_length=10)
        typed: list[float] = Field(default=[1.0, 2.0], max_length=10)

    expected_types = {"bare": int, "typed": float}
    for field_name, expected_type in expected_types.items():
        card = CardFactory.build(field_name, RuntimeArrays.model_fields[field_name])
        qtbot.addWidget(card)
        assert isinstance(card, ListFieldCard)
        assert card._inner_type() is expected_type


SOURCE = """from pydantic import BaseModel, Field


class ProcessParameters(BaseModel):
    label: str = Field(default="run")
"""


def test_invalid_array_default_blocks_editor_write(
    tmp_path: Path,
    qtbot: QtBot,
) -> None:
    path = tmp_path / "parameters.py"
    path.write_text(SOURCE, encoding="utf-8")
    window = MainParametersEditor(path=path, class_name="ProcessParameters")
    qtbot.addWidget(window)

    window._add_card(ListVariableBuildMode(name="values"))
    qtbot.waitUntil(lambda: "values: list[str]" in path.read_text(encoding="utf-8"))
    card = window.param_list._cards[-1]
    valid_source = path.read_text(encoding="utf-8")

    card._editors["element_type"].setCurrentText("int")
    qtbot.wait(50)

    assert path.read_text(encoding="utf-8") == valid_source
    assert not card.validate()
    assert "not a valid int" in card._message.text()

    card._editors["default"].setText("1, 2")
    qtbot.waitUntil(lambda: "values: list[int]" in path.read_text(encoding="utf-8"))
    assert card.validate()
