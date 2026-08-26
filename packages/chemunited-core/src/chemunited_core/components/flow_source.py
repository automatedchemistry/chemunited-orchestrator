"""Flow source component — barrel + nozzle model for syringe/pump sources.

Physical model:
  Inventory node (barrel)  ──nozzle (InternalEdge)──  Port 1  ──external tube──  network

When idle the nozzle is closed → Port 1 is a passive dead-end → no passive backflow.
When active the nozzle is open and the Inventory FLOW BC drives exactly flow_rate
through the nozzle to the external network.

GUI: exposes flow_rate in the properties widget; updated via sync_internal_state().
Sim: _inventory_bc.value (m³/s) is read by the hydraulic solver as a Neumann BC
     on the Inventory node. The nozzle resistance_override is propagated each tick
     by resync_component() in the server drain loop.
"""

from dataclasses import dataclass
from typing import Annotated

from chemunited_quantities import (
    ChemQuantityValidator,
    ChemUnitQuantity,
)
from pydantic import Field
from typing_extensions import override

from chemunited_core.common.enums import GroupParameterCategory, PhaseKind
from chemunited_core.compounds import VolumeContentBase

from .component import ComponentData, ComponentMode
from .enums import BoundaryConditionKind, InternalEdgeRole
from .internals import (
    DEFAULT_INVENTORY_KEY,
    InternalEdge,
    InventoryNode,
    Port,
    PortBoundaryCondition,
)


class FlowSourceMode(ComponentMode):
    """User-configurable flow rate for a flow source.
    flow_rate — volumetric flow rate in ml/min (default 0 — idle).
    """

    flow_rate: Annotated[ChemUnitQuantity, ChemQuantityValidator("ml/min")] = Field(
        default=ChemUnitQuantity("0 ml/min"),
        title="Flow Rate",
        description="Volumetric flow rate imposed at the source port.",
        json_schema_extra={
            "group": GroupParameterCategory.STATUS.value,
            "visible": False,
            "editable": False,
        },
    )


@dataclass
class FlowSourceData(ComponentData):
    """Terminal flow source with a barrel, nozzle, and passive Port 1.

    Port 1 has no boundary condition — it is a passive node solved by the network.
    The Inventory node holds a FLOW BC (_inventory_bc) that drives fluid through the
    nozzle to Port 1 and onward.  When idle the nozzle is closed, making Port 1 a
    dead-end with zero passive flow.
    """

    flow_rate: ChemUnitQuantity = ChemUnitQuantity("0 ml/min")

    @property
    def flow_rate_si(self) -> float:
        return float(self.flow_rate.to_base_units().magnitude)  # m³/s

    @override
    def internal_structure(self) -> None:
        self.port_pairs = [(1,)]
        self.ports_by_number = {
            1: Port(number=1, component=self.name)  # passive — no boundary condition
        }
        self._inventory_bc: PortBoundaryCondition = PortBoundaryCondition(
            kind=BoundaryConditionKind.FLOW, value=self.flow_rate_si
        )
        self.internal_edges = {
            (1, "Inventory"): InternalEdge(
                origin_port=1,
                destination_port="Inventory",
                role=InternalEdgeRole.JUNCTION,
            ).close()
        }
        self.internal_inventories = {
            DEFAULT_INVENTORY_KEY: InventoryNode(
                liq_content=VolumeContentBase(phase_kind=PhaseKind.LIQUID),
                gas_content=VolumeContentBase(phase_kind=PhaseKind.GAS),
            )
        }

    @property
    def internal_inventory(self) -> InventoryNode:
        return self.internal_inventories[DEFAULT_INVENTORY_KEY]

    @internal_inventory.setter
    def internal_inventory(self, inventory: InventoryNode | None) -> None:
        self.internal_inventories = (
            {} if inventory is None else {DEFAULT_INVENTORY_KEY: inventory}
        )

    @override
    def sync_internal_state(self) -> None:
        self._inventory_bc.value = self.flow_rate_si
        edge = self.internal_edges[(1, "Inventory")]
        if self.flow_rate_si == 0.0:
            edge.close()
        else:
            edge.open()
