"""Component enumerations shared by chemunited-core, chemunited-execution,
and chemunited-sim. All values are stable identifiers — do not rename them
without updating serialised project files."""

from enum import Enum, StrEnum, auto


class ComponentType(Enum):
    """Classifies a component as electronically controlled or a passive utensil.
    Determines which runtime manager (ElectronicManager / UtensilManager) the
    factory assigns during GUI assembly."""

    ELECTRONIC = auto()
    UTENSIL = auto()


class PortAccess(Enum):
    """Physical mounting position of a hydraulic port on a component body.
    Used by VesselComponentData to distinguish top from bottom ports."""

    BOTTOM = auto()
    TOP = auto()


class InternalEdgeRole(Enum):
    """Hydraulic role of an internal edge within a component subgraph.

    TRANSPORT — physical channel; resistance computed from geometry (Hagen-Poiseuille).
    JUNCTION  — lossless connection linking a port to an inventory node or hub port."""

    TRANSPORT = auto()
    JUNCTION = auto()


class PortClosure(Enum):
    """Physical seal state of a port, configured by the user during platform setup.

    OPEN   — port connects to external tubing or another component.
    CAPPED — physically sealed; solver imposes zero flow, pressure floats."""

    CAPPED = auto()
    OPEN = auto()


class BoundaryConditionKind(StrEnum):
    """Hydraulic boundary condition applied to a port by the sim solver.
    Serialised as a string in project configuration files.

    NONE     — internal node; pressure and flow both solved by the network.
    PRESSURE — fixed pressure (Pa); flow direction and magnitude are solved.
    FLOW     — fixed flow rate (m³/s); pressure is solved.
               A value of zero acts as a closed dead-end node."""

    NONE = "none"
    PRESSURE = "pressure"
    FLOW = "flow"
