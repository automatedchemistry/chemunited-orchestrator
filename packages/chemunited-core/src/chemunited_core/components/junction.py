"""Junction (distributor) component — multi-port flow splitter/combiner.

Represents T-pieces, Y-pieces, and any multi-port junction where flow splits
or merges. Compiles into a star subgraph: all external ports connect to a
central hub port (port 0) via JUNCTION edges. Flow direction at each arm is
determined by the hydraulic solver.

Port positions are distributed evenly around a circle of radius internal_radius
for GUI rendering.

GUI: exposes number_ports in the properties widget (minimum 3, not editable
     after creation).
Sim: all JUNCTION edges are always active — no switching logic required.
     The hub port (0) is a lossless internal node in the hydraulic matrix.
"""

from dataclasses import dataclass
from typing import ClassVar

import numpy as np
from pydantic import Field
from typing_extensions import override

from chemunited_core.common.enums import GroupParameterCategory

from .component import ComponentData, ComponentMode
from .enums import ComponentType, InternalEdgeRole
from .internals import InternalEdge, Port


class JunctionMode(ComponentMode):
    number_ports: int = Field(
        default=3,
        ge=3,
        title="Port Number",
        description="Number of bifurcation of the distributor",
        json_schema_extra={
            "group": GroupParameterCategory.PROPERTY.value,
            "editable": False,
            "creation_editable": True,
        },
    )


@dataclass
class JunctionData(ComponentData):
    """Structural definition of a multi-port flow junction.

    Internal subgraph: N external ports each connected to central hub port 0
    via a JUNCTION edge. Hub port 0 is always open and never carries an
    explicit boundary condition — its pressure is solved by the network.
    """

    COMPONENT_TYPE: ClassVar[ComponentType] = ComponentType.UTENSIL
    number_ports: int = 3
    internal_radius: float = 30

    @override
    def internal_structure(self) -> None:
        self.port_pairs = [(i + 1, 0) for i in range(self.number_ports)]
        self.ports_by_number = {
            0: Port(number=0, component=self.name, show_in_graph=False)
        }
        self.internal_edges = {}
        self.internal_inventories = {}

        angles = np.arange(-np.pi / 2, 3 * np.pi / 2, 2 * np.pi / self.number_ports)
        for i in range(self.number_ports):
            self.ports_by_number[i + 1] = Port(
                number=i + 1,
                component=self.name,
                relative_position=(
                    self.internal_radius * np.cos(angles[i]),
                    self.internal_radius * np.sin(angles[i]),
                ),
            )
            self.internal_edges[(i + 1, 0)] = InternalEdge(
                origin_port=i + 1, destination_port=0, role=InternalEdgeRole.JUNCTION
            )
