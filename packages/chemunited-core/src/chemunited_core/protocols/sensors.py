from typing import Annotated, Literal

from chemunited_quantities import (
    ChemQuantityValidator,
    ChemUnitQuantity,
)
from pydantic import Field, field_validator

from .models import CommandSignature, ComponentProtocol

# --- shared power commands (identical across all sensor-based protocols) ---


class PowerOnParameter(CommandSignature):
    command: str = "power-on"
    method: Literal["GET", "PUT"] = "PUT"


class PowerOffParameter(CommandSignature):
    command: str = "power-off"
    method: Literal["GET", "PUT"] = "PUT"


class SensorProtocolBase(ComponentProtocol):

    def __init__(self, name: str):
        super().__init__(name)
        self.commands["power-on"] = PowerOnParameter
        self.commands["power-off"] = PowerOffParameter


class PhidgetBubbleSensorComponentProtocols(SensorProtocolBase): ...


# --- MFC ---


class GetFlowRateParameter(CommandSignature):
    command: str = "get-flow-rate"
    method: Literal["GET", "PUT"] = "GET"


class SetFlowRateParameter(CommandSignature):
    command: str = "set-flow-rate"
    method: Literal["GET", "PUT"] = "PUT"
    flowrate: Annotated[ChemUnitQuantity, ChemQuantityValidator("ml / min")] = Field(
        title="Flow Rate",
        description="Flow rate setpoint",
        default=ChemUnitQuantity("0 ml / min"),
    )

    @field_validator("flowrate")
    @classmethod
    def validate_flowrate(cls, v: ChemUnitQuantity) -> ChemUnitQuantity:
        if v < ChemUnitQuantity("0 ml / min"):
            raise ValueError("Flow rate must be non-negative")
        return v


class StopMFCParameter(CommandSignature):
    command: str = "stop"
    method: Literal["GET", "PUT"] = "PUT"


class MFCComponentProtocols(ComponentProtocol):

    def __init__(self, name: str):
        super().__init__(name)
        self.commands["get-flow-rate"] = GetFlowRateParameter
        self.commands["set-flow-rate"] = SetFlowRateParameter
        self.commands["stop"] = StopMFCParameter


# --- Photo sensor ---


class AcquireSignalParameter(CommandSignature):
    command: str = "acquire-signal"
    method: Literal["GET", "PUT"] = "GET"


class CalibrateZeroParameter(CommandSignature):
    command: str = "calibration"
    method: Literal["GET", "PUT"] = "PUT"


class PhotoSensorProtocols(SensorProtocolBase):

    def __init__(self, name: str):
        super().__init__(name)
        self.commands["acquire-signal"] = AcquireSignalParameter
        self.commands["calibration"] = CalibrateZeroParameter


# --- Pressure sensor (read-only) ---


class ReadPressureParameter(CommandSignature):
    command: str = "read-pressure"
    method: Literal["GET", "PUT"] = "GET"


class PressureSensorProtocols(SensorProtocolBase):

    def __init__(self, name: str):
        super().__init__(name)
        self.commands["read-pressure"] = ReadPressureParameter


# --- Pressure control (read + set) ---


class GetPressureParameter(CommandSignature):
    command: str = "pressure"
    method: Literal["GET", "PUT"] = "GET"


class TargetPressureReachedParameter(CommandSignature):
    command: str = "target-reached"
    method: Literal["GET", "PUT"] = "GET"


class SetPressureParameter(CommandSignature):
    command: str = "pressure"
    method: Literal["GET", "PUT"] = "PUT"
    pressure: Annotated[ChemUnitQuantity, ChemQuantityValidator("mPa")] = Field(
        title="Pressure",
        description="Pressure setpoint",
        default=ChemUnitQuantity("0 mPa"),
    )

    @field_validator("pressure")
    @classmethod
    def validate_pressure(cls, v: ChemUnitQuantity) -> ChemUnitQuantity:
        if v < ChemUnitQuantity("0 mPa"):
            raise ValueError("Pressure must be non-negative")
        return v


class PressureControlProtocols(SensorProtocolBase):

    def __init__(self, name: str):
        super().__init__(name)
        self.commands["pressure"] = GetPressureParameter
        self.commands["target-reached"] = TargetPressureReachedParameter
        self.commands["set-pressure"] = SetPressureParameter
