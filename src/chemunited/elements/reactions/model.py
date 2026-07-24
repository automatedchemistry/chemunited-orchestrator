from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ReactionDefinition(BaseModel):
    """Serializable definition of a reaction attached to a platform component."""

    model_config = ConfigDict(frozen=True)

    target: str = Field(min_length=1)
    reaction_type: Literal["FirstOrderDecay"] = "FirstOrderDecay"
    reactant: str = Field(min_length=1)
    product: str = Field(min_length=1)
    rate_constant: float = Field(gt=0.0)
    phase: Literal["LIQUID", "GAS"] = "LIQUID"
    delta_temperature_per_mol_converted: float = 0.0

    @field_validator("rate_constant", "delta_temperature_per_mol_converted")
    @classmethod
    def require_finite_number(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("Value must be finite.")
        return value

    @model_validator(mode="after")
    def require_distinct_species(self):
        if self.reactant == self.product:
            raise ValueError("Reactant and product must be different compounds.")
        return self
