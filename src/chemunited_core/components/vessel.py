"""Vessel component — closed storage container with top and bottom port access.

Represents flasks, reactors, and any closed vessel that holds liquid and gas
simultaneously. Compiles into a star subgraph where all hydraulic ports connect
to a single named InventoryNode via JUNCTION edges.

GUI: exposes capacity, top_access, and bottom_access in the properties widget.
Sim: DigitalTwinAdapter reads InventoryNode initial conditions to seed runtime
     phase inventories; port access (TOP/BOTTOM) is available for future
     phase-preferential routing extensions.
"""

from dataclasses import dataclass
from typing import Annotated, ClassVar

import numpy as np
from chemunited_quantities import (
    ChemQuantityValidator,
    ChemUnitQuantity,
)
from pydantic import Field, field_validator
from typing_extensions import override

from chemunited_core.common.constant import ATMOSPHERE_PRESSURE_PA
from chemunited_core.common.enums import (
    ConnectionType,
    GroupParameterCategory,
    PhaseKind,
)
from chemunited_core.compounds import VolumeContentBase

from .component import ComponentData, ComponentMode
from .enums import BoundaryConditionKind, ComponentType, InternalEdgeRole, PortAccess
from .internals import (
    DEFAULT_INVENTORY_KEY,
    InternalEdge,
    InventoryNode,
    Port,
    PortBoundaryCondition,
)


class VesselMode(ComponentMode):
    """User-configurable parameters for a vessel component.
    capacity     — total geometric volume of the vessel.
    top_access   — number of hydraulic ports at the top (gas side).
    bottom_access — number of hydraulic ports at the bottom (liquid side).
    """

    capacity: Annotated[ChemUnitQuantity, ChemQuantityValidator("ml")] = Field(
        default=ChemUnitQuantity("1 ml"),
        title="Component Capacity",
        description="Volumetric capacity of the component",
        json_schema_extra={
            "group": GroupParameterCategory.PROPERTY.value,
        },
    )
    top_access: int = Field(
        default=1,
        ge=1,
        title="Access at the top",
        description="Access connections at the top of the flask.",
        json_schema_extra={
            "group": GroupParameterCategory.PROPERTY.value,
            "editable": False,
            "creation_editable": True,
            "lock_reason": "Internal Chosen",
        },
    )
    bottom_access: int = Field(
        default=1,
        ge=1,
        title="Access at the bottom",
        description="Access connections at the bottom of the flask.",
        json_schema_extra={
            "group": GroupParameterCategory.PROPERTY.value,
            "editable": False,
            "creation_editable": True,
            "lock_reason": "Internal Chosen",
        },
    )
    heat_exchange: bool = Field(
        default=False,
        title="Heat Exchange",
        description="Whether the component allows heat exchange.",
        json_schema_extra={
            "group": GroupParameterCategory.PROPERTY.value,
            "editable": False,
            "creation_editable": True,
            "lock_reason": "Internal Chosen",
        },
    )
    pressure_access: bool = Field(
        default=False,
        title="Pressure Access",
        description="Whether the component allows air pressure access.",
        json_schema_extra={
            "group": GroupParameterCategory.PROPERTY.value,
            "editable": False,
            "creation_editable": True,
            "lock_reason": "Internal Chosen",
        },
    )
    surface_temperature: Annotated[ChemUnitQuantity, ChemQuantityValidator("K")] = (
        Field(
            default=ChemUnitQuantity("298.15 K"),
            title="Surface Temperature",
            description="Temperature of the vessel surface.",
            json_schema_extra={
                "group": GroupParameterCategory.STATUS.value,
            },
        )
    )
    heat_transfer_coefficient: Annotated[
        ChemUnitQuantity, ChemQuantityValidator("W/(m^2*K)")
    ] = Field(
        default=ChemUnitQuantity("1000 W/(m^2*K)"),
        # typical value for a well-mixed vessel with good thermal contact
        title="Heat Transfer Coefficient",
        description="Heat transfer coefficient for the vessel surface.",
        json_schema_extra={
            "group": GroupParameterCategory.PROPERTY.value,
        },
    )
    diameter: Annotated[ChemUnitQuantity, ChemQuantityValidator("m")] = Field(
        default=ChemUnitQuantity("0.05 m"),
        title="Diameter",
        description="Diameter of the component.",
        json_schema_extra={
            "group": GroupParameterCategory.PROPERTY.value,
        },
    )

    @field_validator("heat_transfer_coefficient")
    @classmethod
    def validate_heat_transfer_coefficient(
        cls, value: ChemUnitQuantity
    ) -> ChemUnitQuantity:
        if value < ChemUnitQuantity("0 W/(m^2*K)"):
            raise ValueError("heat_transfer_coefficient must be >= 0 W/(m^2*K).")
        return value

    @field_validator("diameter")
    @classmethod
    def validate_diameter(cls, value: ChemUnitQuantity) -> ChemUnitQuantity:
        if value <= ChemUnitQuantity("0 m"):
            raise ValueError("diameter must be greater than 0 m.")
        return value


def _centered_offsets(count: int) -> list[float]:
    center = (12 * count - 1) / 2
    return [12 * index - center for index in range(count)]


@dataclass
class VesselComponentData(ComponentData):
    """Structural definition of a closed vessel with phase-separated inventory.

    Internal subgraph: each hydraulic port connects to one named InventoryNode
    via a JUNCTION edge. The inventory node holds separate initial conditions
    for liquid and gas phases — both are seeded from capacity at construction
    (all gas, no liquid by default).

    A HEAT port is always added as the last port for thermal connections.
    """

    COMPONENT_TYPE: ClassVar[ComponentType] = ComponentType.UTENSIL
    capacity: ChemUnitQuantity = ChemUnitQuantity("1 ml")
    top_access: int = 1
    bottom_access: int = 1
    pressure_access: bool = False
    heat_exchange: bool = False
    surface_temperature: ChemUnitQuantity = ChemUnitQuantity("298.15 K")
    heat_transfer_coefficient: ChemUnitQuantity = ChemUnitQuantity("1000 W/(m^2*K)")
    diameter: ChemUnitQuantity = ChemUnitQuantity("0.05 m")

    @property
    def capacity_value(self) -> float:
        return float(self.capacity.to_base_units().magnitude)

    @property
    def heat_transfer_coefficient_value(self) -> float:
        return float(self.heat_transfer_coefficient.to_base_units().magnitude)

    @property
    def temperature_value(self) -> float:
        return float(self.surface_temperature.to_base_units().magnitude)

    @property
    def diameter_value(self) -> float:
        return float(self.diameter.to_base_units().magnitude)

    @property
    def contact_area(self) -> float:
        radius = self.diameter_value / 2
        Area_bottom = np.pi * radius**2
        level_height = self.capacity_value / (np.pi * radius**2)
        Area_side = np.pi * level_height * radius
        return Area_bottom + Area_side

    @override
    def internal_structure(self) -> None:
        n = self.top_access + self.bottom_access
        self.port_pairs = [(i + 1,) for i in range(n + 1)]
        self.ports_by_number = {}
        self.internal_edges = {}

        for number, x_offset in enumerate(_centered_offsets(self.top_access), start=1):
            self.ports_by_number[number] = Port(
                number=number,
                component=self.name,
                access=PortAccess.TOP,
                relative_position=(x_offset, -55),
            )

        for number, x_offset in enumerate(
            _centered_offsets(self.bottom_access),
            start=self.top_access + 1,
        ):
            self.ports_by_number[number] = Port(
                number=number,
                component=self.name,
                access=PortAccess.BOTTOM,
                relative_position=(x_offset, 50),
            )

        if self.heat_exchange:
            m = len(self.ports_by_number)
            self.ports_by_number[m + 1] = Port(
                number=m + 1,
                component=self.name,
                category=ConnectionType.HEAT,
                relative_position=(32, 0.0),
            )

        for number in range(1, n + 1):
            self.internal_edges[(number, DEFAULT_INVENTORY_KEY)] = InternalEdge(
                origin_port=number,
                destination_port=DEFAULT_INVENTORY_KEY,
                role=InternalEdgeRole.JUNCTION,
            )

        self.internal_inventories = {
            DEFAULT_INVENTORY_KEY: InventoryNode(
                gas_content=VolumeContentBase(volume=self.capacity_value),
                liq_content=VolumeContentBase(
                    volume=0, phase_kind=PhaseKind.LIQUID
                ),  # init empty
            )
        }

        if not self.pressure_access:
            atmo_bc = PortBoundaryCondition(
                kind=BoundaryConditionKind.PRESSURE,
                value=float(ATMOSPHERE_PRESSURE_PA),
            )
            for port in self.ports_by_number.values():
                if port.category == ConnectionType.HYDRAULIC:
                    port.boundary = atmo_bc

    @override
    def sync_internal_state(self) -> None:
        inventory = self.internal_inventories.get(DEFAULT_INVENTORY_KEY)
        if inventory is not None:
            inventory.gas_content.volume = self.capacity_value
