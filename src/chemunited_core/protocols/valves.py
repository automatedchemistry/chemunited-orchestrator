from functools import cache
from pathlib import Path
from typing import ClassVar, Literal, cast

from loguru import logger
from pydantic import Field, create_model, field_validator
from pydantic.config import JsonDict

from chemunited_core.components.valve import possibles_connections_pairs
from chemunited_core.utils.file_loading import load_class

from .models import CommandSignature, ComponentProtocol

# --- Rotary valves ---


class MonitorPositionParameter(CommandSignature):
    command: str = "monitor_position"
    method: Literal["GET", "PUT"] = "GET"


class PositionParameter(CommandSignature):
    command: str = "position"
    method: Literal["GET", "PUT"] = "PUT"
    connect: str = Field(
        title="Connect",
        description="Ports to connect",
        default="[[0, 1]]",
        json_schema_extra=cast(
            JsonDict, {"Options": []}
        ),  # options injected per subclass
    )
    disconnect: str = Field(
        title="Disconnect",
        description="Ports to disconnect",
        default="",
    )

    @field_validator("disconnect")
    @classmethod
    def validate_disconnect(cls, v: str) -> str:
        if v == "":
            return v
        # TODO: validate that v is a valid port pair list
        return v


class ValvesProtocols(ComponentProtocol):
    STATOR_PORTS: ClassVar[list[tuple]] = [(1, 2), (0,)]
    ROTOR_PORTS: ClassVar[list[tuple]] = [(3, None), (3,)]
    DEFAULT: ClassVar[str] = "[[0, 1]]"

    @classmethod
    @cache
    def _position_class(cls) -> type[PositionParameter]:
        stator, rotor = cls._load_port_topology()
        options = [
            f"[[{a}, {b}]]"
            for a, b in sorted(possibles_connections_pairs(stator, rotor))
        ]
        return create_model(
            f"{cls.__name__}PositionParameter",
            __base__=PositionParameter,
            connect=(
                str,
                Field(
                    title="Connect",
                    description="Ports to connect",
                    default=cls.DEFAULT,
                    json_schema_extra=cast(JsonDict, {"Options": options}),
                ),
            ),
        )

    @classmethod
    def _load_port_topology(cls) -> tuple[list[tuple], list[tuple]]:
        import chemunited_core.figure_registry.rotary_valve as rv_module

        try:
            data = load_class(
                file_path=Path(rv_module.__file__),
                class_name=f"{cls.__name__[:-9]}Data",
            )
        except Exception as exc:
            logger.debug(f"Falling back to default topology for {cls.__name__}: {exc}")
            data = None
        if data is not None:
            instance = data()
            return instance.stator_ports, instance.rotor_ports
        return cls.STATOR_PORTS, cls.ROTOR_PORTS

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.commands["monitor_position"] = MonitorPositionParameter
        self.commands["position"] = self.__class__._position_class()


class TwoPortDistributionValveProtocols(ValvesProtocols): ...


class FourPortDistributionValveProtocols(ValvesProtocols): ...


class SixPortDistributionValveProtocols(ValvesProtocols): ...


class TwelvePortDistributionValveProtocols(ValvesProtocols): ...


class SixteenPortDistributionValveProtocols(ValvesProtocols): ...


class ThreePortTwoPositionValveProtocols(ValvesProtocols):
    DEFAULT = "[[1, 2]]"


class ThreePortFourPositionValveProtocols(ValvesProtocols):
    DEFAULT = "[[1, 2]]"


class FourPortFivePositionValveProtocols(ValvesProtocols):
    DEFAULT = "[[1, 2]]"


class SixPortTwoPositionValveProtocols(ValvesProtocols):
    DEFAULT = "[[1, 2]]"


# --- Solenoid valves ---


class SolenoidOpenParameter(CommandSignature):
    command: str = "open"
    method: Literal["GET", "PUT"] = "PUT"


class SolenoidCloseParameter(CommandSignature):
    command: str = "close"
    method: Literal["GET", "PUT"] = "PUT"


class SolenoidIsOpenParameter(CommandSignature):
    command: str = "is_open"
    method: Literal["GET", "PUT"] = "GET"


class SolenoidValveProtocols(ComponentProtocol):

    def __init__(self, name: str):
        super().__init__(name)
        self.commands["open"] = SolenoidOpenParameter
        self.commands["close"] = SolenoidCloseParameter
        self.commands["is_open"] = SolenoidIsOpenParameter


class SolenoidValve2WayProtocols(SolenoidValveProtocols): ...


if __name__ == "__main__":
    valve = SixteenPortDistributionValveProtocols("test")
    print(valve.commands["position"].__dict__["__pydantic_fields__"]["connect"])
