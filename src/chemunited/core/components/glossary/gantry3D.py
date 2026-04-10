from dataclasses import dataclass
from typing import override

from pydantic import Field, field_validator

from chemunited.core.common.constant import PATTERN_DIMENSION
from chemunited.core.common.enums import ConnectionType, GroupParameterCategory
from chemunited.core.components.component import (
    ComponentData,
    ComponentMode,
)
from chemunited.core.components.internals import Port
import numpy as np


class gantry3DMode(ComponentMode):
    position_x: str = Field(
        default="1",
        title="Actual position at x axis",
        description="The actual position on the x-axis can be '1', '2', and so on. ",
        examples=["1", "2", "3"],
        json_schema_extra={"group": GroupParameterCategory.STATUS.value},
    )
    position_y: str = Field(
        default="A",
        title="Actual position at y axis",
        description="The actual position on the y-axis can be 'A', 'B', and so on. ",
        examples=["A", "B", "C"],
        json_schema_extra={"group": GroupParameterCategory.STATUS.value},
    )
    position_z: str = Field(
        default="UP",
        title="Actual position at z axis",
        description="The actual position on the y-axis can be 'UP', and 'DOWN'. ",
        examples=["UP", "DOWN"],
        json_schema_extra={
            "group": GroupParameterCategory.STATUS.value,
            "Options": ["UP", "DOWN"],
        },
    )
    connections_number: int = Field(
        default=40,
        gt=0,
        title="Movement connections numbers",
        description="The number of movement connections in the gantry that need to be connected to the others components.",
        json_schema_extra={
            "group": GroupParameterCategory.PROPERTY.value,
            "editable": False,
        },
    )

    @field_validator("position_x")
    def validate_x(cls, value: str) -> str:
        if not value.isdigit() or int(value) <= 0:
            raise ValueError(
                "position_x must be a digit greater than 0 (e.g. '1', '2', ...)."
            )
        return value

    @field_validator("position_y")
    def validate_y(cls, value: str) -> str:
        if not (len(value) == 1 and value.isalpha() and value.isupper()):
            raise ValueError(
                "position_y must be a single uppercase letter (e.g. 'A', 'B', ...)."
            )
        return value

    @field_validator("position_z")
    def validate_z(cls, value: str) -> str:
        if value not in {"UP", "DOWN"}:
            raise ValueError("position_z must be either 'UP' or 'DOWN'.")
        return value


@dataclass
class gantry3DData(ComponentData):
    position_x: str = "1"
    position_y: str = "A"
    position_z: str = "UP"
    connections_number: int = 40

    @override
    def internal_structure(self):
        self.port_pairs = [(1, i + 2) for i in range(self.connections_number)]
        self.ports_by_number = {
            1: Port(
                number=1,
                component=self.name,
                relative_position=(0, - 1.05 * PATTERN_DIMENSION),
            )
        }
        factor_y = 1
        factor_x = 0
        for i in range(self.connections_number):
            if i % 20 == 0:
                factor_x = 0
                factor_y += 0.3
            self.ports_by_number[i + 2] = Port(
                number=i + 2,
                component=self.name,
                category=ConnectionType.MOVEMENT,
                relative_position=(
                    factor_x - 2 * PATTERN_DIMENSION, 
                    factor_y * PATTERN_DIMENSION + 10
                ),
                show_in_graph=False,
            )
            factor_x += 10
