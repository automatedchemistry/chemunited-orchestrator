import uuid
from typing import Any, Literal, Self, Type

from chemunited_core.utils.internal_quantity import (
    ChemUnitQuantity,  # type: ignore[import-not-found]
)
from pydantic import BaseModel, Field


class CommandSignature(BaseModel):
    component: str
    command: str = ""
    method: Literal["GET", "PUT"] = "PUT"
    description: str = ""
    wait_time: float = 0.0
    wait_feedback_status: bool = False
    feedback_status_command: str = ""
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:6])
    feedback_answer: str = "true"

    @property
    def resume_id(self) -> str:
        return f"{self.component}-{self.command}-{self.id}"

    @property
    def has_feedback(self) -> bool:
        return bool(self.feedback_status_command)

    @property
    def parameters(self) -> dict[str, Any]:
        base_fields = set(CommandSignature.model_fields)
        return {
            name: getattr(self, name)
            for name in type(self).model_fields
            if name not in base_fields
        }

    _SCRIPT_EXCLUDED = frozenset({"id", "component", "command", "method"})

    @property
    def line_script(self) -> str:
        method = "put" if self.method == "PUT" else "get"
        base_fields = set(CommandSignature.model_fields)
        all_fields = type(self).model_fields
        params = {n: getattr(self, n) for n in all_fields if n not in base_fields}
        base_kwargs = {
            n: getattr(self, n)
            for n in all_fields
            if n in base_fields and n not in self._SCRIPT_EXCLUDED
        }
        parameters = ", ".join(
            (
                f'{name}="{value}"'
                if isinstance(value, ChemUnitQuantity)
                else f"{name}={value!r}"
            )
            for name, value in {**params, **base_kwargs}.items()
        )
        if parameters:
            return (
                f"self.platform[{self.component!r}].{method}"
                f"({self.command!r}, {parameters})"
            )
        return f"self.platform[{self.component!r}].{method}({self.command!r})"

    def validate_feedback_answer(self, answer: Any) -> bool:
        return answer == self.feedback_answer


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
