import uuid
from typing import Any, Literal, Self, Type

from pydantic import BaseModel, Field

from chemunited_quantities import ChemUnitQuantity


class CommandSignature(BaseModel):
    component: str
    command: str = ""
    method: Literal["GET", "PUT"] = "PUT"
    description: str = ""
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:6])
    param_refs: dict[str, str] = Field(
        default_factory=dict,
        json_schema_extra={"visible": False, "editable": False},
    )

    @property
    def resume_id(self) -> str:
        return f"{self.component}-{self.command}-{self.id}"

    @property
    def parameters(self) -> dict[str, Any]:
        base_fields = set(CommandSignature.model_fields)
        return {
            name: getattr(self, name)
            for name in type(self).model_fields
            if name not in base_fields
        }

    _SCRIPT_EXCLUDED = frozenset({"id", "component", "command", "method", "param_refs"})

    def _fmt_param(self, name: str, value: Any) -> str:
        if name in self.param_refs:
            return f"{name}={self.param_refs[name]}"
        if isinstance(value, ChemUnitQuantity):
            return f'{name}="{value}"'
        return f"{name}={value!r}"

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
            self._fmt_param(name, value)
            for name, value in {**params, **base_kwargs}.items()
        )
        if parameters:
            return (
                f"self.platform[{self.component!r}].{method}"
                f"({self.command!r}, {parameters})"
            )
        return f"self.platform[{self.component!r}].{method}({self.command!r})"


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
