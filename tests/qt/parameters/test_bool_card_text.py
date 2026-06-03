from __future__ import annotations

from pydantic import BaseModel, Field
from pytestqt.qtbot import QtBot

from chemunited.qt.shared.editor.parameters.cards import generate_field_code
from chemunited.qt.shared.editor.parameters.main import field_info_to_build_mode
from chemunited.qt.shared.widgets.base_mode_editor.card_factory import CardFactory
from chemunited.qt.shared.widgets.base_mode_editor.cards.builder_models import (
    BoolVariableBuildMode,
)


class ValveSettings(BaseModel):
    valve_position: bool = Field(
        default=True,
        title="Position 1/2",
        description="The actual valve position.",
        json_schema_extra={
            "group": "Identification",
            "on_text": "Position 1",
            "off_text": "Position 2",
        },
    )


def test_bool_card_uses_custom_switch_text(qtbot: QtBot) -> None:
    field_info = ValveSettings.model_fields["valve_position"]
    card = CardFactory.build("valve_position", field_info)
    qtbot.addWidget(card)

    card.set_value(True)
    assert card._switch.getOnText() == "Position 1"
    assert card._switch.getText() == "Position 1"

    card.set_value(False)
    assert card._switch.getOffText() == "Position 2"
    assert card._switch.getText() == "Position 2"


def test_bool_card_overrides_can_customize_switch_text(qtbot: QtBot) -> None:
    field_info = ValveSettings.model_fields["valve_position"]
    card = CardFactory.build(
        "valve_position",
        field_info,
        extras_override={"on_text": "Open", "off_text": "Closed"},
    )
    qtbot.addWidget(card)

    card.set_value(True)
    assert card._switch.getText() == "Open"

    card.set_value(False)
    assert card._switch.getText() == "Closed"


def test_bool_build_mode_round_trips_custom_switch_text() -> None:
    field_info = ValveSettings.model_fields["valve_position"]
    mode = field_info_to_build_mode("valve_position", field_info)

    assert isinstance(mode, BoolVariableBuildMode)
    assert mode.on_text == "Position 1"
    assert mode.off_text == "Position 2"

    code = generate_field_code(mode)
    assert "'on_text': 'Position 1'" in code
    assert "'off_text': 'Position 2'" in code
