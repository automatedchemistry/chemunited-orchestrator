"""Pressure control component — terminal node that imposes a fixed pressure.

Represents pressurised sources such as gas lines, pressurised reservoirs, or
any element that holds a constant pressure at its connection point. Flow
direction and magnitude are determined entirely by the surrounding network.

GUI: exposes setpoint in the properties widget; updated via sync_internal_state().
Sim: port.boundary.value (Pa) is read by the hydraulic solver as a Dirichlet
     boundary condition — the strongest constraint in the network.
"""
from chemunited_core.utils.internal_quantity import ChemQuantityValidator, ChemUnitQuantity
from chemunited_core.common.enums import GroupParameterCategory
from pydantic import Field
from .component import ComponentData, ComponentMode
from .internals import Port, PortBoundaryCondition
from .enums import BoundaryConditionKind
from typing import Annotated
from dataclasses import dataclass


class PressureControlMode(ComponentMode):
    """User-configurable pressure setpoint.
    setpoint — absolute pressure imposed at the port (default 1 bar).
    """
    setpoint: Annotated[ChemUnitQuantity, ChemQuantityValidator("bar")] = Field(
        default=ChemUnitQuantity("1 bar"),
        title="Pressure Setpoint",
        description="Pressure imposed at the outlet port.",
        json_schema_extra={
            "group": GroupParameterCategory.PROPERTY.value,
        },
    )


@dataclass
class PressureControlData(ComponentData):
    """Structural definition of a terminal pressure source node.

    Single port with BoundaryConditionKind.PRESSURE. No internal edges.
    sync_internal_state() updates the port boundary value when the
    user changes setpoint in the GUI.
    """
    setpoint: ChemUnitQuantity

    @property
    def setpoint_pa(self) -> float:
        return self.setpoint.to_base_units().magnitude

    def internal_structure(self):
        self.port_pairs = [(1,)]
        self.ports_by_number = {
            1: Port(
                number=1,
                component=self.name,
                boundary=PortBoundaryCondition(
                    kind=BoundaryConditionKind.PRESSURE,
                    value=self.setpoint_pa
                )
            )
        }
        self.internal_edges = {}
        self.internal_inventory = None

    def sync_internal_state(self):
        port = self.ports_by_number.get(1)
        port.boundary.kind = BoundaryConditionKind.PRESSURE
        port.boundary.value = self.setpoint_pa
