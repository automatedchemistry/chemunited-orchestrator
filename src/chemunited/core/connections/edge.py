from dataclasses import dataclass
from typing import Annotated

import numpy as np
from pydantic import AliasChoices, BaseModel, Field, model_validator

from ..common.enums import ConnectionType, GroupParameterCategory
from ..common.metadata import Element
from ..utils.internal_quantity import ChemQuantityValidator, ChemUnitQuantity


# Pydantic for validation
class EdgeMode(BaseModel, populate_by_name=True):
    """
    Represents an edge (connection) between two process nodes in the orchestrator.

    This model defines the properties of a connection (edge) such as origin,
    destination, classification type, and physical/visual attributes. It
    includes validation rules to enforce consistency based on the type of
    classification.

    Attributes
    ----------
    origin : str
        Identifier of the starting node.
    destination : str
        Identifier of the target node.
    origin_port : int, default=1
        Port index at the origin node (must be >= 0).
    destination_port : int, default=1
        Port index at the destination node (must be >= 0).
    classification : ConnectionType, default=ConnectionType.FLOW
        Type of connection (flow, movement, heat, or electronic).
    length : ChemUnitQuantity, default=ChemUnitQuantity("100 mm")
        Length of the connection. Must be >= 0.
    diameter : ChemUnitQuantity, default=ChemUnitQuantity("1 mm")
        Diameter of the connection. Must be >= 0.
    straight_path : bool, default=True
        Whether the edge is represented visually as a straight line.
    air_pressure_line : bool, default=False
        Whether the edge represents an air pressure line.

    Validation Rules
    ----------------
    - If `classification` is not `FLOW`, then both `length` and `diameter`
      must be set to 0. Otherwise, a validation error is raised.
    """

    origin: str = Field(
        default="",
        title="Origin component",
        description="Edge source component",
        json_schema_extra={
            "group": GroupParameterCategory.GENERAL.value,
            "editable": False,
            "lock_reason": "Graph built internally",
        },
    )
    destination: str = Field(
        default="",
        title="Destination component",
        description="Edge target component",
        validation_alias=AliasChoices("destination", "destiny"),
        json_schema_extra={
            "group": GroupParameterCategory.GENERAL.value,
            "editable": False,
            "callable": False,
            "lock_reason": "Graph built internally",
        },
    )
    origin_port: int = Field(
        default=1,
        ge=0,
        title="Origin connection point",
        description="Edge source component connection point",
        json_schema_extra={
            "group": GroupParameterCategory.GENERAL.value,
            "editable": False,
            "callable": False,
            "lock_reason": "Graph built internally",
        },
    )
    destination_port: int = Field(
        default=1,
        ge=0,
        title="Destination connection point",
        description="Edge target component connection point",
        validation_alias=AliasChoices("destination_port", "destiny_port"),
        json_schema_extra={
            "group": GroupParameterCategory.GENERAL.value,
            "editable": False,
            "callable": False,
            "lock_reason": "Graph built internally",
        },
    )
    # classification
    classification: ConnectionType = Field(
        default=ConnectionType.HYDRAULIC,
        title="Classification",
        description="Connection classification on the platform",
        json_schema_extra={
            "group": GroupParameterCategory.GENERAL.value,
            "editable": False,
            "callable": False,
            "lock_reason": "Graph built internally",
        },
    )
    # properties
    length: Annotated[ChemUnitQuantity, ChemQuantityValidator("mm")] = Field(
        default=ChemUnitQuantity("100 mm"),
        title="Length",
        description="Length of the connection",
        json_schema_extra={
            "group": GroupParameterCategory.PROPERTY.value,
        },
    )
    diameter: Annotated[ChemUnitQuantity, ChemQuantityValidator("mm")] = Field(
        default=ChemUnitQuantity("1 mm"),
        title="Diameter",
        description="Diameter of the connection",
        json_schema_extra={
            "group": GroupParameterCategory.PROPERTY.value,
        },
    )
    # Visual properties
    straight_path: bool = Field(
        default=True,
        title="Connection shape",
        description="Connection shape - curved or straight",
        json_schema_extra={
            "group": GroupParameterCategory.PROPERTY.value,
            "on_text": "Straight",
            "off_text": "Curved",
        },
    )
    air_pressure_line: bool = Field(
        default=False,
        title="Connection function",
        description="Connection function - air or liquid",
        json_schema_extra={
            "group": GroupParameterCategory.PROPERTY.value,
            "on_text": "Pressure Air",
            "off_text": "Liquid",
        },
    )

    @model_validator(mode="after")
    def check_flow_rules(self) -> "EdgeMode":
        """Ensure that non-flow connections have length and diameter set to 0."""
        if self.classification != ConnectionType.HYDRAULIC:
            self.length = ChemUnitQuantity("0 mm")
            self.diameter = ChemUnitQuantity("0 mm")

        return self

    @property
    def destiny(self) -> str:
        return self.destination

    @property
    def destiny_port(self) -> int:
        return self.destination_port


@dataclass
class EdgeData(Element):
    origin: str
    destination: str
    origin_port: int
    destination_port: int
    classification: ConnectionType
    length: ChemUnitQuantity
    diameter: ChemUnitQuantity
    straight_path: bool = True
    air_pressure_line: bool = False

    @property
    def name(self) -> str:
        return (
            f"{self.origin}_{self.origin_port}_"
            f"{self.destination}_{self.destination_port}"
        )

    @property
    def capacity(self) -> float:
        """capacity in SI"""
        return self.length_value * np.pi * self.diameter**2 / 4  # m**3

    @property
    def length_value(self) -> float:
        return self.length.to_base_units().magnitude

    @property
    def diameter_value(self) -> float:
        return self.diameter.to_base_units().magnitude
