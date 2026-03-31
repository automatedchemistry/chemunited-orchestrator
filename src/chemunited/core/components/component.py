"""Base classes for all component definitions in chemunited-core.

ComponentMode  — Pydantic model; defines the user-editable parameter schema
                rendered by the GUI properties widget. Persisted to project
                configuration files (TOML/JSON).

ComponentData  — Dataclass; holds the compiled structural state of one
                component instance at runtime. Consumed by the GUI scene
                and by chemunited-sim's DigitalTwinAdapter.

Every concrete component subclasses both and implements internal_structure()
to populate ports, internal edges, and the inventory node.
sync_internal_state() is called when the user updates parameters via the GUI.
"""
from dataclasses import dataclass, field
from typing import ClassVar, Literal

from pydantic import BaseModel, Field, field_validator

from chemunited_core.common.enums import GroupParameterCategory
from chemunited_core.common.metadata import Element

from .enums import ComponentType
from .internals import InternalEdge, InventoryNode, Port

EdgeKey = tuple[int, int | Literal["Inventory"]]


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
        internal_inventory: Lumped control volume; None for non-storage components.
    """
    name: str = ""
    figure: str = ""
    position: tuple[float, float] = (0, 0)
    angle: int = 0
    COMPONENT_TYPE: ClassVar[ComponentType] = ComponentType.ELECTRONIC
    port_pairs: list[tuple[int, ...]] = field(default_factory=list, init=False)
    ports_by_number: dict[int, Port] = field(default_factory=dict, init=False)
    internal_edges: dict[EdgeKey, InternalEdge] = field(
        default_factory=dict, init=False
    )
    internal_inventory: InventoryNode | None = field(default=None, init=False)

    """ Properties """

    @property
    def component_type(self) -> ComponentType:
        return type(self).COMPONENT_TYPE

    @property
    def is_electronic(self) -> bool:
        return self.component_type == ComponentType.ELECTRONIC

    """ Initialization """

    def __post_init__(self):
        self.internal_structure()

    def internal_structure(self):
        self.port_pairs = [(1, 2)]
        self.ports_by_number = {
            1: Port(number=1, component=self.name, relative_position=(-1, 0)),
            2: Port(number=2, component=self.name, relative_position=(1, 0)),
        }
        self.internal_edges = {}
        self.internal_inventory = None


@dataclass
class NeutralComponentData(ComponentData):
    def __post_init__(self): ...
