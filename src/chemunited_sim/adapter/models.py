"""Hydraulic graph data structures for chemunited-sim.

These objects are produced by the adapter and consumed by the hydraulics
solver, transport module, inventory module, and recorder. They carry no
physics logic -- only structural and geometric information.

All physical quantities are in SI units:
    length            -- metres (m)
    diameter          -- metres (m)
    resistance_override -- Pa*s/m3
"""

from __future__ import annotations

from dataclasses import dataclass, field

from chemunited_core.components.enums import InternalEdgeRole
from chemunited_core.components.internals import InventoryNode, PortBoundaryCondition
from chemunited_core.compounds.pockets import VolumeContentBase


@dataclass(frozen=True)
class HeatLink:
    """Thermal-control connection between a provider and a heat-enabled target.

    The provider is a neutral thermal controller (for example a chiller).  The
    target is a component whose wall/surface temperature drives heat exchange.
    """

    provider_component: str
    provider_port: int | str
    target_component: str
    target_port: int | str


@dataclass(frozen=True)
class PowerLink:
    """Electronic energize/de-energize connection between a relay channel and
    a target component's ELECTRONIC port.

    The provider is a multi-channel relay box; each of its channels can drive
    one or more targets (fan-out is allowed). The target's energized state
    tracks the provider channel's ``active`` flag.
    """

    provider_component: str
    provider_port: int | str
    target_component: str
    target_port: int | str


@dataclass(frozen=True)
class HydraulicNode:
    """A single node in the flat hydraulic network graph.

    Represents one of:
    - A component port:         node_id = "component_name.port_number"
    - A vessel inventory node:  node_id = "component_name.Inventory"
    - A routing hub port:       node_id = "component_name.0",  is_hub=True

    Nodes are immutable once compiled. Boundary conditions are copied verbatim
    from Port.boundary at compile time and never mutated.

    Attributes:
        node_id:   Globally unique node identifier.
        boundary:  Hydraulic boundary condition for terminal nodes (pumps,
                   pressure controllers). None means the node is internal --
                   both pressure and flow are solved by the network.
        is_hub:    True for zero-volume routing hubs, such as the central
                   port of a junction or selector valve.
        component: Owning component name, used by the recorder.
    """

    node_id: str
    boundary: PortBoundaryCondition | None
    is_hub: bool
    component: str


@dataclass
class HydraulicEdge:
    """A single directed edge in the flat hydraulic network graph.

    Represents an internal component channel (is_external=False) or an
    external physical tube connecting two component ports (is_external=True).

    The hydraulics solver reads role, length, diameter, resistance_override,
    and forced_flow:
        forced_flow is not None     -> ideal flow source: edge conductance is
                                        0 (excluded from the resistive network)
                                        and the edge's flow is fixed at
                                        forced_flow regardless of the pressure
                                        field on either side.
        role == JUNCTION            -> R = 0 (lossless, geometry ignored)
        resistance_override is not None -> use override directly (Pa*s/m3)
        otherwise                   -> R = (128 * eta * L) / (pi * D^4)

    HydraulicEdge is mutable. The worker writes resistance_override in-place
    for BPR edges each time step and for valve edges after rotor switches,
    and writes forced_flow in-place for Pump edges each time step.

    Attributes:
        edge_id:             Globally unique identifier.
                             Internal: "component_name.origin_port.dest_port"
                             External: EdgeData.name
        origin_node_id:      HydraulicNode.node_id of the source endpoint.
        destination_node_id: HydraulicNode.node_id of the target endpoint.
        length:              Channel length in metres (m). 0.0 for BPR edges.
        diameter:            Channel inner diameter in metres (m). 0.0 for BPR.
        role:                TRANSPORT = resistance from geometry.
                             JUNCTION  = lossless, R = 0.
        resistance_override: None = compute from geometry.
                             float = use directly (Pa*s/m3).
                             R_MAX_HYDRAULIC = hard-closed, zero-conductance channel.
        forced_flow:         None = flow is solved from resistance as normal.
                             float = ideal flow source (m3/s); see decision
                             tree above. Mutually exclusive with a closed edge.
        component:           Owning component name; None for external edges.
        is_external:         True for edges derived from EdgeData (physical tubing).
    """

    edge_id: str
    origin_node_id: str
    destination_node_id: str
    length: float
    diameter: float
    role: InternalEdgeRole
    resistance_override: float | None
    component: str | None
    is_external: bool
    content: list[VolumeContentBase] = field(default_factory=list)
    forced_flow: float | None = None


@dataclass
class HydraulicGraph:
    """Flat hydraulic network graph produced by compile_graph.

    Contains all hydraulic nodes and edges for the entire platform.
    The hydraulics solver, transport module, inventory module, and recorder
    all consume this object -- they do not read chemunited-core objects directly.

    Attributes:
        nodes:           All hydraulic nodes keyed by node_id.
        edges:           All hydraulic edges keyed by edge_id. Dict for O(1)
                         lookup when the worker updates BPR or valve edges.
        inventory_nodes: Snapshot-copied InventoryNode objects keyed by
                         "component_name.Inventory". Deep-copied at compile
                         time -- subsequent sync_internal_state() calls on
                         the source component do not affect these copies.
                         Used by the inventory module to seed InventoryState.
    """

    nodes: dict[str, HydraulicNode] = field(default_factory=dict)
    edges: dict[str, HydraulicEdge] = field(default_factory=dict)
    inventory_nodes: dict[str, InventoryNode] = field(default_factory=dict)
    heat_links: list[HeatLink] = field(default_factory=list)
    power_links: list[PowerLink] = field(default_factory=list)
