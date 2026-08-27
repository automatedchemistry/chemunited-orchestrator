from typing import Annotated, Literal

from pydantic import Field, field_validator

from chemunited_quantities import (
    ChemQuantityValidator,
    ChemUnitQuantity,
)

from .models import CommandSignature, ComponentProtocol


class IsPumpingParameter(CommandSignature):
    command: str = "is-pumping"
    method: Literal["GET", "PUT"] = "GET"


class InfuseParameter(CommandSignature):
    command: str = "infuse"
    method: Literal["GET", "PUT"] = "PUT"
    rate: Annotated[ChemUnitQuantity, ChemQuantityValidator("ml / min")] = Field(
        title="Flow Rate",
        description="Flow rate of the pump",
        default=ChemUnitQuantity("1 ml / min"),
    )
    volume: Annotated[ChemUnitQuantity, ChemQuantityValidator("ml")] = Field(
        title="Volume",
        description="Volume to infuse",
        default=ChemUnitQuantity("1 ml"),
    )


class StopPumpParameter(CommandSignature):
    command: str = "stop"
    method: Literal["GET", "PUT"] = "PUT"


class PumpProtocols(ComponentProtocol):

    def __init__(self, name: str):
        super().__init__(name)
        self.commands["is-pumping"] = IsPumpingParameter
        self.commands["infuse"] = InfuseParameter
        self.commands["stop"] = StopPumpParameter


class HPLCPumpProtocols(PumpProtocols): ...


class WithdrawParameter(CommandSignature):
    command: str = "withdraw"
    method: Literal["GET", "PUT"] = "PUT"
    rate: Annotated[ChemUnitQuantity, ChemQuantityValidator("ml / min")] = Field(
        title="Flow Rate",
        description="Flow rate of the pump",
        default=ChemUnitQuantity("1 ml / min"),
    )
    volume: Annotated[ChemUnitQuantity, ChemQuantityValidator("ml")] = Field(
        title="Volume",
        description="Volume to withdraw",
        default=ChemUnitQuantity("1 ml"),
    )

    @field_validator("rate")
    @classmethod
    def validate_positive_rate(cls, v: ChemUnitQuantity) -> ChemUnitQuantity:
        if v <= ChemUnitQuantity("0 ml / min"):
            raise ValueError("Value must be positive")
        return v

    @field_validator("volume")
    @classmethod
    def validate_positive_volume(cls, v: ChemUnitQuantity) -> ChemUnitQuantity:
        if v <= ChemUnitQuantity("0 ml"):
            raise ValueError("Value must be positive")
        return v


class SyringePumpProtocols(PumpProtocols):

    def __init__(self, name: str):
        super().__init__(name)
        self.commands["withdraw"] = WithdrawParameter
