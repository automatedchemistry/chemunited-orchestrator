"""Back-pressure regulator (BPR) component — pressure-controlled inline valve.

Holds upstream pressure above a user-defined setpoint. The internal edge starts
closed (R_MAX_HYDRAULIC). The sim adapter opens it each time step when upstream
pressure meets or exceeds the setpoint, and closes it otherwise.

This introduces a pressure-dependent nonlinearity into the hydraulic solve.
The adapter resolves this by iterating until the active edge set stabilises.

A BPR is physically a one-way check valve: it relieves pressure upstream to
downstream only and can never carry flow the other way. The sim worker
(chemunited_sim.worker.runner.Worker._reseat_backward_bpr_edges) enforces
this by force-closing and re-solving past any open BPR edge whose solved
flow comes out negative, every tick, before that flow can be recorded or
used elsewhere.

GUI: exposes setpoint in the properties widget.
Sim: setpoint_pa is read by the adapter each time step to evaluate the
     open/close condition. Edge resistance is set via close() / open().
"""

from dataclasses import dataclass
from typing import Annotated, ClassVar

from pydantic import Field
from typing_extensions import override

from chemunited_core.common.enums import GroupParameterCategory
from chemunited_quantities import (
    ChemQuantityValidator,
    ChemUnitQuantity,
)

from .component import ComponentData, ComponentMode
from .enums import ComponentType, InternalEdgeRole
from .internals import InternalEdge, Port


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

    COMPONENT_TYPE: ClassVar[ComponentType] = ComponentType.UTENSIL
    setpoint: ChemUnitQuantity = ChemUnitQuantity("1 bar")

    @property
    def setpoint_pa(self) -> float:
        """Setpoint in Pascals for the hydraulic solver."""
        return float(self.setpoint.to_base_units().magnitude)

    @override
    def internal_structure(self) -> None:
        self.port_pairs = [(1, 2)]
        self.ports_by_number = {
            1: Port(number=1, component=self.name),  # upstream
            2: Port(number=2, component=self.name),  # downstream
        }
        self.internal_edges = {
            (1, 2): InternalEdge(
                origin_port=1,
                destination_port=2,
                role=InternalEdgeRole.JUNCTION,
            ).close()
        }
        self.internal_inventories = {}
