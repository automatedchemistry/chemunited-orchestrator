from dataclasses import MISSING, Field, dataclass, fields, is_dataclass
from typing import Self

from pydantic import BaseModel


@dataclass
class Element:
    @staticmethod
    def _ensure_mode(mode: BaseModel, method_name: str) -> None:
        if not isinstance(mode, BaseModel):
            raise TypeError(
                f"{method_name} expects a Pydantic BaseModel instance, "
                f"got {type(mode).__name__}."
            )

    @classmethod
    def _ensure_dataclass_type(cls) -> None:
        if not is_dataclass(cls):
            raise TypeError(f"{cls.__name__} must be a dataclass to use this method.")

    @staticmethod
    def _has_default(field: Field) -> bool:
        return field.default is not MISSING or field.default_factory is not MISSING

    @classmethod
    def _mode_to_init_values(
        cls,
        mode: BaseModel,
        *,
        require_all: bool,
        explicit_only: bool,
    ) -> dict[str, object]:
        init_values: dict[str, object] = {}
        missing_fields: list[str] = []
        provided_fields = mode.model_fields_set if explicit_only else set()

        for field in fields(cls):
            if not field.init:
                continue

            if explicit_only and field.name not in provided_fields:
                continue

            if hasattr(mode, field.name):
                init_values[field.name] = getattr(mode, field.name)
                continue

            if require_all and not cls._has_default(field):
                missing_fields.append(field.name)

        if missing_fields:
            missing_names = ", ".join(f"'{name}'" for name in missing_fields)
            raise TypeError(
                f"Cannot build {cls.__name__} from {type(mode).__name__}: "
                f"missing required field(s) {missing_names}."
            )

        return init_values

    @classmethod
    def from_mode(cls: type[Self], mode: BaseModel) -> Self:
        cls._ensure_mode(mode, f"{cls.__name__}.from_mode")
        cls._ensure_dataclass_type()
        init_values = cls._mode_to_init_values(
            mode,
            require_all=True,
            explicit_only=False,
        )
        return cls(**init_values)

    def update(self: Self, mode: BaseModel) -> Self:
        cls = type(self)
        cls._ensure_mode(mode, f"{cls.__name__}.update")
        cls._ensure_dataclass_type()

        updates = cls._mode_to_init_values(
            mode,
            require_all=False,
            explicit_only=True,
        )
        for name, value in updates.items():
            setattr(self, name, value)

        self.sync_internal_state()

        return self

    def sync_internal_state(self) -> None: ...
