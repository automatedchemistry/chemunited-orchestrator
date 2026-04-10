import uuid
from typing import Literal, Self, Type

from pydantic import BaseModel, Field


class CommandSignature(BaseModel):
    component: str
    command: str = ""
    method: Literal["GET", "PUT"] = "PUT"
    description: str = ""
    wait_time: float = 0.0
    wait_feedback_status: bool = False
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:6])

    @property
    def result(self) -> str:
        return f"{self.component}-{self.command}-{self.id}"

    @property
    def has_feedback(self) -> bool:
        return False


class ComponentProtocol:
    def __init__(self, name: str):
        self.name = name
        self.commands: dict[str, Type[CommandSignature]] = {}
        self._instances: dict[str, CommandSignature] = {}

    def sync(self) -> Self:
        for command in self.commands:
            self._instances[command] = self.commands[command](component=self.name)
        return self

    @property
    def get_commands(self) -> dict[str, CommandSignature]:
        return {k: v for k, v in self._instances.items() if v.method == "GET"}

    @property
    def put_commands(self) -> dict[str, CommandSignature]:
        return {k: v for k, v in self._instances.items() if v.method == "PUT"}
