"""Vessel component — closed storage container with top and bottom port access.

Represents flasks, reactors, and any closed vessel that holds liquid and gas
simultaneously. Compiles into a star subgraph where all hydraulic ports connect
to a single InventoryNode via JUNCTION edges.

GUI: exposes capacity, top_access, and bottom_access in the properties widget.
Sim: DigitalTwinAdapter reads InventoryNode initial conditions to seed runtime
     phase inventories; port access (TOP/BOTTOM) is available for future
     phase-preferential routing extensions.
"""
from dataclasses import dataclass
from typing import Annotated

from pydantic import Field

from chemunited_core.common.enums import (
    ConnectionType,
    GroupParameterCategory,
    PhaseKind,
)
from chemunited_core.compounds import VolumeContentBase
from chemunited_core.utils.internal_quantity import (
    ChemQuantityValidator,
    ChemUnitQuantity,
)

from .component import ComponentData, ComponentMode
from .enums import ComponentType, InternalEdgeRole, PortAccess
from .internals import InternalEdge, InventoryNode, Port


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
        default=3,
        ge=1,
        title="Access at the top",
        description="Access connections at the top of the flask.",
        json_schema_extra={
            "group": GroupParameterCategory.PROPERTY.value,
            "editable": False,
            "lock_reason": "Internal Chosen",
        },
    )
    bottom_access: int = Field(
        default=2,
        ge=1,
        title="Access at the bottom",
        description="Access connections at the bottom of the flask.",
        json_schema_extra={
            "group": GroupParameterCategory.PROPERTY.value,
            "editable": False,
            "lock_reason": "Internal Chosen",
        },
    )


def _centered_offsets(count: int) -> list[float]:
    center = (count - 1) / 2
    return [index - center for index in range(count)]


@dataclass
class VesselComponentData(ComponentData):
    """Structural definition of a closed vessel with phase-separated inventory.

    Internal subgraph: each hydraulic port connects to one InventoryNode
    via a JUNCTION edge. The inventory node holds separate initial conditions
    for liquid and gas phases — both are seeded from capacity at construction
    (all gas, no liquid by default).

    A HEAT port is always added as the last port for thermal connections.
    """
    COMPONENT_TYPE = ComponentType.UTENSIL
    capacity: ChemUnitQuantity
    top_access: int
    bottom_access: int

    @property
    def capacity_value(self) -> float:
        return self.capacity.to_base_units().magnitude

    def internal_structure(self):
        n = self.top_access + self.bottom_access
        self.port_pairs = [(i + 1,) for i in range(n + 1)]
        self.ports_by_number = {}
        self.internal_edges = {}

        for number, x_offset in enumerate(_centered_offsets(self.top_access), start=1):
            self.ports_by_number[number] = Port(
                number=number,
                component=self.name,
                access=PortAccess.TOP,
                relative_position=(x_offset, 1.0),
            )

        for number, x_offset in enumerate(
            _centered_offsets(self.bottom_access),
            start=self.top_access + 1,
        ):
            self.ports_by_number[number] = Port(
                number=number,
                component=self.name,
                access=PortAccess.BOTTOM,
                relative_position=(x_offset, -1.0),
            )

        self.ports_by_number[n + 1] = Port(
            number=n + 1,
            component=self.name,
            category=ConnectionType.HEAT,
            relative_position=(-1.5, 0.0),
        )

        for number in range(1, n + 1):
            self.internal_edges[(number, "Inventory")] = InternalEdge(
                origin_port=number,
                destination_port="Inventory",
                role=InternalEdgeRole.JUNCTION,
            )

        self.internal_inventory = InventoryNode(
            gas_content=VolumeContentBase(volume=self.capacity_value),
            liq_content=VolumeContentBase(
                volume=0, phase_kind=PhaseKind.LIQUID
            ),  # init empty
        )

    def sync_internal_state(self):
        self.internal_inventory.gas_content.volume = self.capacity_value
