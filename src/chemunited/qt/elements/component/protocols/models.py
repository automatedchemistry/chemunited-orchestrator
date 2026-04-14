from chemunited.workflow.orchestrator import CommandSignature
from typing import Self, Type


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
