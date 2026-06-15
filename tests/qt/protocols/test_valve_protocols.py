from chemunited.elements.component.protocols.valves import (
    ThreePortTwoPositionValveProtocols,
)


def test_valve_position_command_populates_connect_options() -> None:
    protocol = ThreePortTwoPositionValveProtocols("ValveA").sync()

    position = protocol.put_commands["position"]
    connect_field = type(position).model_fields["connect"]
    extras = connect_field.json_schema_extra or {}
    options = extras.get("Options")

    assert isinstance(options, list)
    assert options == ["[[0, 1]]", "[[0, 2]]"]
    assert all(isinstance(option, str) for option in options)
