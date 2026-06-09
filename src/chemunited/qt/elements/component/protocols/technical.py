from typing import Annotated, Literal

from chemunited_core.utils.internal_quantity import (
    ChemQuantityValidator,
    ChemUnitQuantity,
)
from pydantic import Field

from .models import CommandSignature, ComponentProtocol

# --- Temperature control ---


class GetTemperatureParameter(CommandSignature):
    command: str = "temperature"
    method: Literal["GET", "PUT"] = "GET"


class TargetTemperatureReachedParameter(CommandSignature):
    command: str = "target-reached"
    method: Literal["GET", "PUT"] = "GET"


class SetTemperatureParameter(CommandSignature):
    command: str = "temperature"
    method: Literal["GET", "PUT"] = "PUT"
    description: str = "Set the temperature setpoint"
    temp: Annotated[ChemUnitQuantity, ChemQuantityValidator("C")] = Field(
        title="Temperature",
        description="Temperature setpoint",
        default=ChemUnitQuantity("0 C"),
    )


class TemperatureControlProtocols(ComponentProtocol):

    def __init__(self, name: str):
        super().__init__(name)
        self.commands["temperature"] = GetTemperatureParameter
        self.commands["target-reached"] = TargetTemperatureReachedParameter
        self.commands["set_temperature"] = SetTemperatureParameter

        # TODO: feedback command (poll target-reached after set_temperature)


class PeltierCoolerTemperatureControlProtocols(TemperatureControlProtocols): ...


# --- Length / position control ---


class GetPositionParameter(CommandSignature):
    command: str = "get_position"
    method: Literal["GET", "PUT"] = "GET"


class GetAvailablePositionsParameter(CommandSignature):
    command: str = "get_available_positions"
    method: Literal["GET", "PUT"] = "GET"


class SetPositionParameter(CommandSignature):
    command: str = "set_position"
    method: Literal["GET", "PUT"] = "PUT"
    description: str = "Set the position setpoint"
    position: str = Field(
        title="Position",
        description="Target position",
        default="A",
    )


class LengthControlProtocols(ComponentProtocol):

    def __init__(self, name: str):
        super().__init__(name)
        self.commands["get_position"] = GetPositionParameter
        self.commands["get_available_positions"] = GetAvailablePositionsParameter
        self.commands["set_position"] = SetPositionParameter


# --- Multi-channel ADC ---


class ReadChannelParameter(CommandSignature):
    command: str = "read"
    method: Literal["GET", "PUT"] = "GET"
    channel: str = Field(
        title="Channel",
        description="Channel number",
        default="1",
        pattern=r"^\d+$",
    )


class ReadAllChannelsParameter(CommandSignature):
    command: str = "read_all"
    method: Literal["GET", "PUT"] = "GET"


class MultiChannelADCProtocols(ComponentProtocol):

    def __init__(self, name: str):
        super().__init__(name)
        self.commands["read"] = ReadChannelParameter
        self.commands["read_all"] = ReadAllChannelsParameter


# --- Multi-channel DAC ---


class SetChannelVoltageParameter(CommandSignature):
    command: str = "set"
    method: Literal["GET", "PUT"] = "PUT"
    description: str = "Set the voltage of a specific channel"
    channel: str = Field(
        title="Channel",
        description="Channel number",
        default="1",
        pattern=r"^\d+$",
    )
    value: Annotated[ChemUnitQuantity, ChemQuantityValidator("V")] = Field(
        title="Value",
        description="Voltage to set",
        default=ChemUnitQuantity("0 V"),
    )


class MultiChannelDACProtocols(ComponentProtocol):

    def __init__(self, name: str):
        super().__init__(name)
        self.commands["read"] = ReadChannelParameter  # reuse — identical structure
        self.commands["set"] = SetChannelVoltageParameter


# --- Multi-channel relay ---


class RelayChannelOnParameter(CommandSignature):
    command: str = "power-on"
    method: Literal["GET", "PUT"] = "PUT"
    channel: str = Field(
        title="Channel",
        description="Channel number",
        default="1",
        pattern=r"^\d+$",
    )


class RelayChannelOffParameter(CommandSignature):
    command: str = "power-off"
    method: Literal["GET", "PUT"] = "PUT"
    channel: str = Field(
        title="Channel",
        description="Channel number",
        default="1",
        pattern=r"^\d+$",
    )


class RelayMultipleChannelParameter(CommandSignature):
    command: str = "multiple_channel"
    method: Literal["GET", "PUT"] = "PUT"
    values: str = Field(
        title="Values",
        description=(
            "List of up to 'n' integers (0, 1, or 2). "
            'Example: "00010012". '
            "If shorter than 'n', remaining channels are set to 0. "
            "Any value greater than 0 is treated as ON."
        ),
        default="000",
    )


class ReadChannelSetPointParameter(CommandSignature):
    command: str = "read_channel_set_point"
    method: Literal["GET", "PUT"] = "GET"
    channel: str = Field(
        title="Channel",
        description="Channel number",
        default="1",
        pattern=r"^\d+$",
    )


class ReadChannelsSetPointParameter(CommandSignature):
    command: str = "read_channels_set_point"
    method: Literal["GET", "PUT"] = "GET"


class MultiChannelRelayProtocols(ComponentProtocol):

    def __init__(self, name: str):
        super().__init__(name)
        self.commands["power-on"] = RelayChannelOnParameter
        self.commands["power-off"] = RelayChannelOffParameter
        self.commands["multiple_channel"] = RelayMultipleChannelParameter
        self.commands["read_channel_set_point"] = ReadChannelSetPointParameter
        self.commands["read_channels_set_point"] = ReadChannelsSetPointParameter


# --- PhotoReactor ---


class ReadIntensityParameter(CommandSignature):
    command: str = "read_intensity"
    method: Literal["GET", "PUT"] = "GET"


class SetIntensityParameter(CommandSignature):
    command: str = "set_intensity"
    method: Literal["GET", "PUT"] = "PUT"
    percent: int = Field(
        title="Percentage",
        description="Light intensity from 0 to 100",
        default=0,
        ge=0,
        le=100,
    )


class DevicePowerOnParameter(CommandSignature):
    command: str = "power-on"
    method: Literal["GET", "PUT"] = "PUT"


class DevicePowerOffParameter(CommandSignature):
    command: str = "power-off"
    method: Literal["GET", "PUT"] = "PUT"


class PhotoReactorProtocols(ComponentProtocol):

    def __init__(self, name: str):
        super().__init__(name)
        self.commands["read_intensity"] = ReadIntensityParameter
        self.commands["set_intensity"] = SetIntensityParameter
        self.commands["power-on"] = DevicePowerOnParameter
        self.commands["power-off"] = DevicePowerOffParameter


# --- Power switch / control ---


class PowerSwitchProtocols(ComponentProtocol):

    def __init__(self, name: str):
        super().__init__(name)
        self.commands["power-on"] = DevicePowerOnParameter
        self.commands["power-off"] = DevicePowerOffParameter


class PhidgetBubbleSensorPowerComponentProtocols(PowerSwitchProtocols): ...


class ReadCurrentParameter(CommandSignature):
    command: str = "read_current"
    method: Literal["GET", "PUT"] = "GET"


class ReadVoltageParameter(CommandSignature):
    command: str = "read_voltage"
    method: Literal["GET", "PUT"] = "GET"


class SetCurrentParameter(CommandSignature):
    command: str = "set_current"
    method: Literal["GET", "PUT"] = "PUT"
    current: Annotated[ChemUnitQuantity, ChemQuantityValidator("mA")] = Field(
        title="Current",
        description="Current setpoint",
        default=ChemUnitQuantity("0 mA"),
    )


class SetVoltageParameter(CommandSignature):
    command: str = "set_voltage"
    method: Literal["GET", "PUT"] = "PUT"
    voltage: Annotated[ChemUnitQuantity, ChemQuantityValidator("V")] = Field(
        title="Voltage",
        description="Voltage setpoint",
        default=ChemUnitQuantity("0 V"),
    )


class PowerControlProtocols(PowerSwitchProtocols):

    def __init__(self, name: str):
        super().__init__(name)
        self.commands["read_current"] = ReadCurrentParameter
        self.commands["read_voltage"] = ReadVoltageParameter
        self.commands["set_current"] = SetCurrentParameter
        self.commands["set_voltage"] = SetVoltageParameter
