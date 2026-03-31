"""Back-pressure regulator (BPR) component — pressure-controlled inline valve.

Holds upstream pressure above a user-defined setpoint. The internal edge starts
closed (R_MAX_HYDRAULIC). The sim adapter opens it each time step when upstream
pressure meets or exceeds the setpoint, and closes it otherwise.

This introduces a pressure-dependent nonlinearity into the hydraulic solve.
The adapter resolves this by iterating until the active edge set stabilises.

GUI: exposes setpoint in the properties widget.
Sim: setpoint_pa is read by the adapter each time step to evaluate the
     open/close condition. Edge resistance is set via close() / open().
"""
from chemunited_core.utils.internal_quantity import ChemQuantityValidator, ChemUnitQuantity
from chemunited_core.common.enums import GroupParameterCategory
from pydantic import Field
from .component import ComponentData, ComponentMode
from .internals import Port, InternalEdge
from typing import Annotated
from dataclasses import dataclass


class BackPressureRegulatorMode(ComponentMode):
    setpoint: Annotated[ChemUnitQuantity, ChemQuantityValidator("bar")] = Field(
        default=ChemUnitQuantity("1 bar"),
        title="Pressure Setpoint",
        description="Upstream pressure required to open the regulator.",
        json_schema_extra={
            "group": GroupParameterCategory.PROPERTY.value,
        },
    )

@dataclass
class BackPressureRegulatorData(ComponentData):
    """Structural definition of a back-pressure regulator.

    Two ports (upstream port 1, downstream port 2) connected by a single
    TRANSPORT edge. Edge starts closed — the sim adapter toggles it each
    time step based on the upstream pressure vs. setpoint comparison.
    """
    setpoint: ChemUnitQuantity

    @property
    def setpoint_pa(self) -> float:
        """Setpoint in Pascals for the hydraulic solver."""
        return self.setpoint.to_base_units().magnitude

    def internal_structure(self):
        self.port_pairs = [(1, 2)]
        self.ports_by_number = {
            1: Port(number=1, component=self.name),  # upstream
            2: Port(number=2, component=self.name),  # downstream
        }
        self.internal_edges = {
            (1, 2): InternalEdge(
                origin_port=1,
                destination_port=2,
            ).close()
        }
        self.internal_inventory = None
