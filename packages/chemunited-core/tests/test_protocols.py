"""Functional tests for chemunited_core.protocols."""

from __future__ import annotations

import pytest

from chemunited_core.protocols import (
    CommandSignature,
    Gantry1DProtocols,
    Gantry3DProtocols,
    HPLCControlProtocols,
    HPLCPumpProtocols,
    MFCComponentProtocols,
    MultiChannelADCProtocols,
    NMRControlProtocols,
    PressureControlProtocols,
    SixPortTwoPositionValveProtocols,
    SyringePumpProtocols,
    TemperatureControlProtocols,
)
from chemunited_quantities import ChemUnitQuantity


class TestCommandSignature:
    def test_defaults(self) -> None:
        cmd = CommandSignature(component="Pump")
        assert cmd.component == "Pump"
        assert cmd.method == "PUT"
        assert len(cmd.id) == 6

    def test_resume_id(self) -> None:
        cmd = CommandSignature(component="Pump", command="infuse")
        assert cmd.resume_id.startswith("Pump-infuse-")

    def test_parameters_empty_for_base(self) -> None:
        cmd = CommandSignature(component="Pump")
        assert cmd.parameters == {}

    def test_line_script_no_params(self) -> None:
        cmd = CommandSignature(component="Pump", command="stop", method="PUT")
        script = cmd.line_script
        assert "platform['Pump'].put('stop'" in script

    def test_line_script_get(self) -> None:
        cmd = CommandSignature(component="Pump", command="status", method="GET")
        assert ".get(" in cmd.line_script


class TestComponentProtocol:
    def test_sync_populates_instances(self) -> None:
        proto = HPLCControlProtocols("hplc1")
        proto.sync()
        assert "send-method" in proto._instances
        assert "run-sample" in proto._instances

    def test_get_commands_filter(self) -> None:
        proto = HPLCPumpProtocols("pump1")
        proto.sync()
        get_cmds = proto.get_commands
        assert all(v.method == "GET" for v in get_cmds.values())

    def test_put_commands_filter(self) -> None:
        proto = HPLCPumpProtocols("pump1")
        proto.sync()
        put_cmds = proto.put_commands
        assert all(v.method == "PUT" for v in put_cmds.values())


class TestPumpProtocols:
    def test_hplc_pump_commands(self) -> None:
        proto = HPLCPumpProtocols("p1")
        assert set(proto.commands) >= {"is-pumping", "infuse", "stop"}

    def test_syringe_pump_has_withdraw(self) -> None:
        proto = SyringePumpProtocols("p1")
        assert "withdraw" in proto.commands

    def test_infuse_unit_quantity(self) -> None:
        from chemunited_core.protocols.pumps import InfuseParameter

        cmd = InfuseParameter(
            component="Pump",
            rate=ChemUnitQuantity("5 ml / min"),
            volume=ChemUnitQuantity("2 ml"),
        )
        assert cmd.rate == ChemUnitQuantity("5 ml / min")

    def test_withdraw_positive_rate_validator(self) -> None:
        from chemunited_core.protocols.pumps import WithdrawParameter

        with pytest.raises(Exception):
            WithdrawParameter(
                component="Pump",
                rate=ChemUnitQuantity("0 ml / min"),
                volume=ChemUnitQuantity("1 ml"),
            )

    def test_line_script_with_unit_quantity(self) -> None:
        from chemunited_core.protocols.pumps import StopPumpParameter

        cmd = StopPumpParameter(component="Pump")
        assert "platform" in cmd.line_script
        assert "stop" in cmd.line_script


class TestSensorProtocols:
    def test_mfc_commands(self) -> None:
        proto = MFCComponentProtocols("mfc1")
        assert set(proto.commands) >= {"get-flow-rate", "set-flow-rate", "stop"}

    def test_pressure_control_commands(self) -> None:
        proto = PressureControlProtocols("pr1")
        assert "pressure" in proto.commands
        assert "target-reached" in proto.commands


class TestTechnicalProtocols:
    def test_temperature_control(self) -> None:
        proto = TemperatureControlProtocols("tc1")
        assert "temperature" in proto.commands
        assert "target-reached" in proto.commands
        assert "set_temperature" in proto.commands

    def test_set_temperature_accepts_offset_unit_string(self) -> None:
        command_type = TemperatureControlProtocols("tc1").commands["set_temperature"]

        command = command_type(component="tc1", temp="10 degC")

        assert command.temp.to("degC").magnitude == pytest.approx(10)

    def test_multichannel_adc(self) -> None:
        proto = MultiChannelADCProtocols("adc1")
        assert set(proto.commands) >= {"read", "read_all"}


class TestAssemblyProtocols:
    def test_gantry1d_commands(self) -> None:
        proto = Gantry1DProtocols("g1")

        assert set(proto.commands) == {
            "get:position",
            "position",
            "available_positions",
            "home",
            "stop",
            "limits",
            "target-reached",
        }
        assert proto.commands["get:position"].model_fields["command"].default == (
            "position"
        )
        assert proto.commands["get:position"].model_fields["method"].default == "GET"
        assert proto.commands["position"].model_fields["command"].default == "position"
        assert proto.commands["position"].model_fields["method"].default == "PUT"

    def test_gantry3d_commands_are_unchanged(self) -> None:
        proto = Gantry3DProtocols("g3")

        assert set(proto.commands) == {
            "set_x_position",
            "set_y_position",
            "set_z_position",
        }


class TestAnalyticsProtocols:
    def test_nmr_commands(self) -> None:
        proto = NMRControlProtocols("nmr1")
        assert set(proto.commands) >= {
            "solvent",
            "sample-name",
            "user-data",
            "protocol-list",
            "spectrum-folder",
            "is-busy",
            "acquire-spectrum",
            "stop",
        }


class TestValveProtocols:
    def test_six_port_two_position_initializes(self) -> None:
        proto = SixPortTwoPositionValveProtocols("v1")
        assert "monitor_position" in proto.commands
        assert "position" in proto.commands

    def test_position_options_are_strings(self) -> None:
        proto = SixPortTwoPositionValveProtocols("v1")
        pos_cls = proto.commands["position"]
        field_info = pos_cls.model_fields["connect"]
        options = (field_info.json_schema_extra or {}).get("Options", [])
        assert isinstance(options, list)
        assert len(options) > 0
        assert all(isinstance(o, str) for o in options)

    def test_getattr_lookup_via_module(self) -> None:
        import chemunited_core.protocols as pm

        cls = getattr(pm, "SixPortTwoPositionValveProtocols", None)
        assert cls is not None
        proto = cls("v1")
        assert proto.commands
