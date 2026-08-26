from chemunited_core.protocols import CommandSignature, ComponentProtocol
from chemunited_core.protocols.pumps import HPLCPumpProtocols

from chemunited.connectivity.openapi_commands import merge_openapi_commands


def test_openapi_routes_create_plain_string_command_signatures() -> None:
    protocol = ComponentProtocol("PumpA")
    added = merge_openapi_commands(
        protocol=protocol,
        openapi={
            "paths": {
                "/Pump/device/custom-command/{slot}": {
                    "parameters": [{"name": "slot", "in": "path"}],
                    "get": {
                        "parameters": [{"name": "sample_id", "in": "query"}],
                    },
                },
                "/Pump/device/set-flow-rate": {
                    "put": {
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "properties": {
                                            "rate": {"type": "number"},
                                            "unit": {"type": "string"},
                                        }
                                    }
                                }
                            }
                        }
                    },
                },
            }
        },
        device="Pump",
        component="device",
    )

    assert added == 2
    get_cls = protocol.commands["custom-command/{slot}"]
    put_cls = protocol.commands["set-flow-rate"]
    assert issubclass(get_cls, CommandSignature)
    assert get_cls.model_fields["command"].default == "custom-command/{slot}"
    assert get_cls.model_fields["method"].default == "GET"
    assert get_cls.model_fields["slot"].annotation is str
    assert get_cls.model_fields["sample_id"].annotation is str
    assert put_cls.model_fields["method"].default == "PUT"
    assert put_cls.model_fields["rate"].annotation is str
    assert put_cls.model_fields["unit"].annotation is str


def test_openapi_commands_skip_predefined_protocol_coverage() -> None:
    protocol = HPLCPumpProtocols("PumpA")

    added = merge_openapi_commands(
        protocol=protocol,
        openapi={
            "paths": {
                "/Pump/device/infuse": {"put": {}},
                "/Pump/device/prime": {"put": {}},
            }
        },
        device="Pump",
        component="device",
    )

    assert added == 1
    assert "prime" in protocol.commands
    infuse_matches = [
        command_class
        for command_class in protocol.commands.values()
        if command_class.model_fields["command"].default == "infuse"
        and command_class.model_fields["method"].default == "PUT"
    ]
    assert len(infuse_matches) == 1


def test_openapi_commands_skip_unrelated_and_unsupported_paths() -> None:
    protocol = ComponentProtocol("PumpA")

    added = merge_openapi_commands(
        protocol=protocol,
        openapi={
            "paths": {
                "/startup_config": {"get": {}},
                "/Pump": {"get": {}},
                "/Other/device/custom": {"get": {}},
                "/Pump/device/custom": {"post": {}},
            }
        },
        device="Pump",
        component="device",
    )

    assert added == 0
    assert protocol.commands == {}
