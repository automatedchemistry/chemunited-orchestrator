from typing import Literal

from pydantic import Field

from .models import CommandSignature, ComponentProtocol


class GetPositionParameter(CommandSignature):
    command: str = "position"
    method: Literal["GET", "PUT"] = "GET"


class SetPositionParameter(CommandSignature):
    command: str = "position"
    method: Literal["GET", "PUT"] = "PUT"
    position: str = Field(
        title="Position",
        description="Named or raw position for a single-axis gantry.",
        default="1",
    )


class GetAvailablePositionsParameter(CommandSignature):
    command: str = "available_positions"
    method: Literal["GET", "PUT"] = "GET"


class HomeParameter(CommandSignature):
    command: str = "home"
    method: Literal["GET", "PUT"] = "PUT"
    wait: bool = Field(
        title="Wait",
        description="Wait until the homing procedure finishes.",
        default=True,
    )
    timeout: float = Field(
        title="Timeout",
        description="Maximum time to wait for homing.",
        default=60.0,
    )


class StopParameter(CommandSignature):
    command: str = "stop"
    method: Literal["GET", "PUT"] = "PUT"


class LimitsParameter(CommandSignature):
    command: str = "limits"
    method: Literal["GET", "PUT"] = "GET"


class TargetReachedParameter(CommandSignature):
    command: str = "target-reached"
    method: Literal["GET", "PUT"] = "GET"


class SetXPositionParameter(CommandSignature):
    command: str = "set_x_position"
    method: Literal["GET", "PUT"] = "PUT"
    position: str = Field(
        title="Position X",
        description="Position along the X axis of the tray.",
        default="1",
        pattern=r"^\d+$",
    )


class SetYPositionParameter(CommandSignature):
    command: str = "set_y_position"
    method: Literal["GET", "PUT"] = "PUT"
    position: str = Field(
        title="Position Y",
        description="Position along the Y axis of the tray.",
        default="A",
        pattern=r"^[A-Z]+$",
    )


class SetZPositionParameter(CommandSignature):
    command: str = "set_z_position"
    method: Literal["GET", "PUT"] = "PUT"
    position: str = Field(
        title="Position Z",
        description="Vertical position of the head.",
        default="DOWN",
        json_schema_extra={"options": ["UP", "DOWN"]},
    )


class Gantry1DProtocols(ComponentProtocol):

    def __init__(self, name: str):
        super().__init__(name)
        self.commands["get:position"] = GetPositionParameter
        self.commands["position"] = SetPositionParameter
        self.commands["available_positions"] = GetAvailablePositionsParameter
        self.commands["home"] = HomeParameter
        self.commands["stop"] = StopParameter
        self.commands["limits"] = LimitsParameter
        self.commands["target-reached"] = TargetReachedParameter


class Gantry3DProtocols(ComponentProtocol):

    def __init__(self, name: str):
        super().__init__(name)
        self.commands["set_x_position"] = SetXPositionParameter
        self.commands["set_y_position"] = SetYPositionParameter
        self.commands["set_z_position"] = SetZPositionParameter
