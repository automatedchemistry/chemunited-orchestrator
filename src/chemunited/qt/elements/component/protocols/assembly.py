from typing import Literal

from pydantic import Field

from .models import CommandSignature, ComponentProtocol


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


class Gantry3DProtocols(ComponentProtocol):

    def __init__(self, name: str):
        super().__init__(name)
        self.commands["set_x_position"] = SetXPositionParameter
        self.commands["set_y_position"] = SetYPositionParameter
        self.commands["set_z_position"] = SetZPositionParameter
