"""Base classes for all component definitions in chemunited-core.

ComponentMode  — Pydantic model; defines the user-editable parameter schema
                rendered by the GUI properties widget. Persisted to project
                configuration files (TOML/JSON).

ComponentData  — Dataclass; holds the compiled structural state of one
                component instance at runtime. Consumed by the GUI scene
                and by chemunited-sim's DigitalTwinAdapter.

Every concrete component subclasses both and implements internal_structure()
to populate ports, internal edges, and inventory nodes.
sync_internal_state() is called when the user updates parameters via the GUI.
"""

from dataclasses import dataclass, field
from typing import ClassVar

from pydantic import BaseModel, Field, field_validator
from typing_extensions import override

from chemunited_core.common.constant import (
    AMBIENT_TEMPERATURE_K,
    ATMOSPHERE_PRESSURE_PA,
)
from chemunited_core.common.enums import GroupParameterCategory, PhaseKind
from chemunited_core.common.metadata import Element
from chemunited_core.compounds.entity import IDEAL_GAS_CONSTANT
from chemunited_core.compounds.pockets import VolumeContentBase

from .command import PutResult
from .enums import ComponentType, InternalEdgeRole
from .internals import (
    DEFAULT_INVENTORY_KEY,
    InternalEdge,
    InternalEndpoint,
    InventoryKey,
    InventoryNode,
    Port,
)

EdgeKey = tuple[int, InternalEndpoint]

PATTERN_DIMENSION = 50


class ComponentMode(BaseModel, populate_by_name=True):
    """User-editable parameter schema for a component.

    Rendered as a properties widget in the GUI Setup Manager.
    Serialised to project configuration files alongside ComponentData.
    Subclass this for each concrete component to declare its configurable fields.
    """

    name: str = Field(
        default="",
        title="Component Name",
        description="Component name in the Orchestration",
        json_schema_extra={
            "group": GroupParameterCategory.GENERAL.value,
            "editable": False,
            "creation_editable": True,
        },
    )
    figure: str = Field(
        default="",
        title="Component Figure",
        description="Component Figure Class Representation",
        json_schema_extra={
            "group": GroupParameterCategory.GENERAL.value,
            "editable": False,
            "callable": False,
            "lock_reason": "Internal Classification",
        },
    )
    position: tuple[float, float] = Field(
        default=(0, 0),
        title="Component Position",
        description="Component Position in the Scene",
        json_schema_extra={"visible": False},
    )
    angle: int = Field(
        default=0,
        ge=0,
        le=360,
        title="Component Angle",
        description="Component Position in the Scene",
        json_schema_extra={"group": GroupParameterCategory.GENERAL.value},
    )
    mirror: bool = Field(
        default=False,
        title="Mirror Component",
        description="Horizontal mirror of the component figure",
        json_schema_extra={"group": GroupParameterCategory.GENERAL.value},
    )

    @field_validator("name")
    def validate_name(cls, value: str) -> str:
        if "." in value or "_" in value:
            raise ValueError("Field 'name' must not contain '.' or '_' characters.")
        return value


@dataclass
class ComponentData(Element):
    """Runtime structural description of a component instance.

    Populated once by internal_structure() on construction, and refreshed
    by sync_internal_state() when the user changes parameters in the GUI.

    Consumed by:
        - GraphComponent (GUI scene item)
        - DigitalTwinAdapter (chemunited-sim) to compile the hydraulic subgraph

    Attributes:
        name:               Unique component identifier within the project.
        figure:             Figure class name used by the GUI factory.
        position:           Scene coordinates for GUI rendering.
        angle:              Rotation angle in degrees (0–360).
        port_pairs:         Valid external connection pairs for topology rules.
        ports_by_number:    All ports indexed by port number.
        internal_edges:     Internal channels keyed by (origin, destination).
        internal_inventories: Lumped control volumes keyed by stable inventory IDs.
    """

    name: str = ""
    figure: str = ""
    position: tuple[float, float] = (0, 0)
    angle: int = 0
    mirror: bool = False
    COMPONENT_TYPE: ClassVar[ComponentType] = ComponentType.ELECTRONIC
    port_pairs: list[tuple[int, ...]] = field(default_factory=list, init=False)
    ports_by_number: dict[int, Port] = field(default_factory=dict, init=False)
    internal_edges: dict[EdgeKey, InternalEdge] = field(
        default_factory=dict, init=False
    )
    internal_inventories: dict[InventoryKey, InventoryNode] = field(
        default_factory=dict, init=False
    )

    """ Properties """

    @property
    def component_type(self) -> ComponentType:
        return type(self).COMPONENT_TYPE

    @property
    def is_electronic(self) -> bool:
        return self.component_type == ComponentType.ELECTRONIC

    @property
    def internal_inventory(self) -> InventoryNode | None:
        """Compatibility alias returning the first internal inventory."""

        return next(iter(self.internal_inventories.values()), None)

    @internal_inventory.setter
    def internal_inventory(self, inventory: InventoryNode | None) -> None:
        """Compatibility setter for old singleton-inventory code."""

        self.internal_inventories = (
            {} if inventory is None else {DEFAULT_INVENTORY_KEY: inventory}
        )

    """ Initialization """

    def __post_init__(self) -> None:
        self.internal_structure()

    def internal_structure(self) -> None:
        self.port_pairs = [(1, 2)]
        self.ports_by_number = {
            1: Port(
                number=1,
                component=self.name,
                relative_position=(-PATTERN_DIMENSION / 2, 0),
            ),
            2: Port(
                number=2,
                component=self.name,
                relative_position=(PATTERN_DIMENSION / 2, 0),
            ),
        }
        self.internal_edges = {
            (1, 2): InternalEdge(
                origin_port=1, destination_port=2, role=InternalEdgeRole.JUNCTION
            )
        }
        self.internal_inventories = {}

    def apply_air_defaults(self) -> None:
        """Fill an empty vessel inventory with air if the user declared nothing.

        No-op when: no inventory, user already declared content, or no capacity_value.
        PlugFlowComponentData overrides this with its own implementation.
        """
        inv = self.internal_inventory
        if inv is None:
            return
        if inv.liq_content.volume + inv.gas_content.volume > 0.0:
            return
        capacity = getattr(self, "capacity_value", 0.0)
        if capacity <= 0.0:
            return
        n_air = (
            ATMOSPHERE_PRESSURE_PA
            * capacity
            / (IDEAL_GAS_CONSTANT * AMBIENT_TEMPERATURE_K)
        )
        inv.gas_content = VolumeContentBase(
            phase_kind=PhaseKind.GAS,
            volume=capacity,
            initial_species={"air": n_air},
            initial_pressure=ATMOSPHERE_PRESSURE_PA,
            initial_temperature=AMBIENT_TEMPERATURE_K,
        )

    """ Commands - status change """

    def put(self, command: str, **kwargs) -> PutResult:
        return PutResult()

    def apply(self, command: str, **kwargs) -> PutResult:
        """Apply a command, mutating runtime state for the live simulation.

        Unlike put() (pure computation), apply() mutates this ComponentData in
        place and MUST call sync_internal_state() whenever it changes a
        parameter. The returned PutResult carries any derived follow-up events
        (e.g. a pump auto-stop scheduled at volume / rate seconds from now) for
        the sim Worker to schedule.

        The base implementation is a no-op returning an empty PutResult, which
        is correct for passive or uncontrolled components (junctions, tubing,
        vessels, sensors, ...). Concrete controllable components override this.
        """
        return PutResult()

    def get(self, command: str, **kwargs) -> object | None:
        return None


@dataclass
class NeutralComponentData(ComponentData):
    @override
    def internal_structure(self) -> None:
        pass
