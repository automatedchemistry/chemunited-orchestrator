"""Flow source component — terminal node that imposes a fixed volumetric flow rate.

Represents any device that drives flow into the network at a controlled rate:
pumps, syringe infusion, mass flow controllers. Has a single port with a FLOW
boundary condition. A flow_rate of zero (default) makes the source idle —
the solver treats it as a closed dead-end node.

GUI: exposes flow_rate in the properties widget; updated via sync_internal_state().
Sim: port.boundary.value (m³/s) is read directly by the hydraulic solver
     as a Neumann boundary condition.
"""
from chemunited_core.utils.internal_quantity import ChemQuantityValidator, ChemUnitQuantity
from chemunited_core.common.enums import GroupParameterCategory
from pydantic import Field
from .component import ComponentData, ComponentMode
from .internals import Port, PortBoundaryCondition
from .enums import BoundaryConditionKind
from typing import Annotated
from dataclasses import dataclass



class FlowSourceMode(ComponentMode):
    """User-configurable flow rate for a flow source.
    flow_rate — volumetric flow rate in ml/min (default 0 — idle).
    """
    flow_rate: Annotated[ChemUnitQuantity, ChemQuantityValidator("ml/min")] = Field(
        default=ChemUnitQuantity("0 ml/min"),
        title="Flow Rate",
        description="Volumetric flow rate imposed at the source port.",
        json_schema_extra={
            "group": GroupParameterCategory.PROPERTY.value,
        },
    )

@dataclass
class FlowSourceData(ComponentData):
    """Structural definition of a terminal flow source node.

    Single port with BoundaryConditionKind.FLOW. No internal edges.
    sync_internal_state() updates the port boundary value when the
    user changes flow_rate in the GUI or via a protocol command.
    """
    flow_rate: ChemUnitQuantity

    @property
    def flow_rate_si(self) -> float:
        return self.flow_rate.to_base_units().magnitude  # m³/s

    def internal_structure(self):
        self.port_pairs = [(1,)]
        self.ports_by_number = {
            1: Port(
                number=1,
                component=self.name,
                boundary=PortBoundaryCondition(
                    kind=BoundaryConditionKind.FLOW,
                    value=self.flow_rate_si
                )
            )
        }
    
    def sync_internal_state(self):
        self.ports_by_number[1].boundary.value = self.flow_rate_si