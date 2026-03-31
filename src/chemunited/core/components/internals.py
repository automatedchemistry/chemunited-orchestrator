"""Structural building blocks for component subgraphs.

Every component in chemunited-core compiles its internal topology into three
object types defined here:

    Port           — external connection point; carries user-configured
                     boundary conditions and physical closure state.
    InternalEdge   — directed channel inside the component subgraph;
                     carries geometry for the hydraulic solver and a
                     resistance override for switching elements.
    InventoryNode  — lumped control volume for storage components (vessels,
                     reactors); carries initial conditions set by the user.

These objects are consumed by:
    - the GUI (Setup Manager) to render ports and expose properties.
    - chemunited-sim (DigitalTwinAdapter) to compile the hydraulic network.

All physical quantities are in SI units unless noted otherwise.
"""

from dataclasses import dataclass, field
from typing import Self

from chemunited_core.common.constant import R_MAX_HYDRAULIC
from chemunited_core.common.enums import ConnectionType
from chemunited_core.compounds import VolumeContentBase

from .enums import BoundaryConditionKind, InternalEdgeRole, PortAccess, PortClosure


@dataclass
class PortBoundaryCondition:
    """Explicit hydraulic boundary condition for a port.

    Only populated for terminal ports that impose a value on the solver
    (flow sources, pressure controls). Internal ports leave this as None.

    Attributes:
        kind:  Type of boundary condition (PRESSURE or FLOW).
        value: Imposed value — Pa for PRESSURE, m³/s for FLOW.
    """
    kind: BoundaryConditionKind = BoundaryConditionKind.NONE
    value: float = 0.0


@dataclass
class Port:
    """External connection point of a component.

    Represents a physical port where tubing or another component attaches.
    The GUI renders ports as connection points on the component figure.
    The sim adapter uses ports as hydraulic nodes in the network graph.

    Attributes:
        number:            Port index within the component (unique per component).
        component:         Name of the owning component.
        category:          Connection type (HYDRAULIC, HEAT, ELECTRONIC, MOVEMENT).
        relative_position: Position offset from the component centre for GUI rendering.
        access:            Physical mounting side (TOP / BOTTOM) — used by vessels.
        closure:           Physical seal state set by the user (OPEN / CAPPED).
        boundary:          Explicit boundary condition; None means internal node.
    """
    number: int
    component: str
    category: ConnectionType = ConnectionType.HYDRAULIC
    relative_position: tuple[float, float] = (0, 0)
    access: PortAccess = PortAccess.TOP
    closure: PortClosure = PortClosure.OPEN
    boundary: PortBoundaryCondition | None = None

    @property
    def name(self) -> str:
        """Fully qualified port identifier: '<component>.<number>'."""
        return f"{self.component}.{self.number}"

    def block(self, value: bool = True) -> None:
        """Convenience method to cap or uncap the port programmatically."""
        self.closure = PortClosure.CAPPED if value else PortClosure.OPEN


@dataclass
class InternalEdge:
    """Directed channel connecting two endpoints within a component subgraph.

    Endpoints are port numbers (int) or the string 'Inventory' for edges that
    connect a port to an InventoryNode. The EdgeKey tuple in ComponentData uses
    the same convention: (origin, destination).

    The sim adapter (chemunited-sim) computes hydraulic resistance from geometry
    using the Hagen-Poiseuille equation unless resistance_override is set.
    Use close() / open() to control flow through switching elements (valves, BPRs).

    Attributes:
        origin_port:         Source endpoint — port number or 'Inventory'.
        destination_port:    Target endpoint — port number or 'Inventory'.
        length:              Channel length in metres (used for resistance calc).
        diameter:            Channel inner diameter in metres (used for resistance calc).
        role:                TRANSPORT (geometry matters) or JUNCTION (lossless).
        resistance_override: Fixed resistance in Pa·s/m³; None = compute from geometry.
    """
    origin_port: int = 1
    destination_port: int | str = 2
    length: float = 1e-3
    diameter: float = 1e-3
    role: InternalEdgeRole = InternalEdgeRole.TRANSPORT
    resistance_override: float | None = None

    @property
    def is_active(self) -> bool:
        """True when resistance is computed from geometry (channel is open)."""
        return self.resistance_override is None

    def close(self) -> Self:
        """Block the channel by setting resistance to R_MAX_HYDRAULIC."""
        self.resistance_override = R_MAX_HYDRAULIC
        return self

    def open(self) -> Self:
        """Unblock the channel — resistance reverts to geometry-based computation."""
        self.resistance_override = None
        return self


@dataclass
class InventoryNode:
    """Lumped control volume for storage components (vessels, reactors).

    Holds the user-configured initial conditions for each phase.
    The sim adapter reads these to seed the runtime inventory state
    (chemunited-sim.InventoryState) at the start of each simulation.

    Incoming parcels of any phase are accepted; the sim adapter routes
    each parcel to the appropriate phase inventory based on parcel.phase_kind.

    Attributes:
        liq_content: Initial state of the liquid phase inventory.
        gas_content: Initial state of the gas phase inventory.
    """
    liq_content: VolumeContentBase = field(default_factory=VolumeContentBase)
    gas_content: VolumeContentBase = field(default_factory=VolumeContentBase)