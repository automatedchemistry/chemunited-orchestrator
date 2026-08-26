# How to Build a New Component

This package models equipment with two Python objects:

- `*Mode`: a Pydantic model for user input, GUI fields, config files, and validation.
- `*Data`: a dataclass for the compiled runtime structure consumed by the GUI and simulation layers.

The lifecycle is:

```text
ComponentMode subclass -> Data.from_mode(mode) -> ComponentData subclass
                                      |
                                      +-> data.update(partial_mode)
                                          -> data.sync_internal_state()
```

Use `*Mode` for values the user can configure. Use `*Data` for the structural result: ports, internal edges, inventories, boundary conditions, and command behavior.

## Building a Component in Your Own Project (recommended for most users)

You do **not** need an editable install of chemunited-core, and you do **not** need to add
anything to this repository, to use a custom component. Everything below still applies to
*writing* the `*Mode`/`*Data` classes — only *where* you put the code and *how* it gets
registered differs.

Create `{your_project}/customizations/components/__init__.py` in your project folder (next to
`draw/` and `protocols/`). It's loaded automatically whenever the project is opened, in both
chemunited-sim and the orchestrator GUI. It should import whatever sibling modules define
your components:

```python
# {your_project}/customizations/components/__init__.py
from . import my_valve
```

```python
# {your_project}/customizations/components/my_valve.py
from chemunited_core.components import ComponentData, ComponentMode
from chemunited_core.components.command import PutResult
from chemunited_core.figure_registry import ComponentDefinition, register_component
from chemunited_core.protocols import ComponentProtocol, CommandSignature, register_protocol


class MyValveMode(ComponentMode):
    ...


class MyValveData(ComponentData):
    # Real, concrete state — anything a custom GraphComponent reads via
    # self.inf (see graph.py below) must be an actual field here, not a
    # placeholder. See "Where Component Code Lives" below for how to also
    # implement internal_structure() / sync_internal_state() if your
    # component's hydraulic topology needs to change with state.
    is_open: bool = False

    def apply(self, command: str, **kwargs) -> PutResult:
        if command == "open":
            self.is_open = True
        elif command == "close":
            self.is_open = False
        self.sync_internal_state()
        return PutResult()


register_component("MyValve", ComponentDefinition(MyValveData, MyValveMode, category="valve"))

# Optional — only for electronically commandable components. Purely declarative:
# no networking code belongs here, just the command names/parameters.
class OpenCommand(CommandSignature):
    command: str = "open"


class CloseCommand(CommandSignature):
    command: str = "close"


class MyValveProtocols(ComponentProtocol):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.commands["open"] = OpenCommand
        self.commands["close"] = CloseCommand


register_protocol("MyValve", MyValveProtocols)
```

Place the SVG next to `my_valve.py`, named `MyValve.svg` (matching `figure_base`, or the
registry name if `figure_base` is omitted) — `register_component()` finds it automatically.
Custom components show up under a dedicated "Custom" group in the orchestrator's component
palette, distinct from the built-in catalog below.

If your component needs multiple composited SVG layers, animation, or appearance that
changes with commands, add `{your_project}/customizations/components/graph.py` defining a
subclass of the orchestrator's `GraphComponent` (the same base class every built-in component
with bespoke rendering, e.g. rotary valves, already uses):

```python
# {your_project}/customizations/components/graph.py
from chemunited.elements.component.graph_item import GraphComponent
from .my_valve import MyValveData


class MyValveGraph(GraphComponent[MyValveData]):
    FIGURE = "MyValve"

    def build(self) -> None:
        super().build()
        self._build_svg("MyValveHandle")  # extra composited layer

    def sync_visuals(self) -> None:
        self._svg.setRotation(90 if self.inf.is_open else 0)
```

`customizations/components/graph.py` is orchestrator-only (it imports PyQt5) — never import it
from `customizations/components/__init__.py`, since chemunited-sim's headless loader must not
see it. It's loaded separately, after your component registration, so `from . import my_valve`
inside it resolves correctly.

Extra composited layers like `"MyValveHandle"` above don't need their own `register_component()`
call — just place `MyValveHandle.svg` anywhere in `components/`, the same as the primary
figure. Every `.svg` file in that folder is automatically discoverable by filename.

`register_component`/`register_protocol` raise if the name is already taken (built-in or
otherwise) unless you pass `override=True` — this catches accidental clashes early.

The rest of this document explains how to *contribute* a component to chemunited-core's own
shared catalog, so it ships with the package for every project. Use the project-local path
above unless you specifically want that.

## Where Component Code Lives

Core component abstractions live under `src/chemunited_core/components/`.

Important files:

- `component.py`: base `ComponentMode` and `ComponentData`.
- `internals.py`: `Port`, `InternalEdge`, `InventoryNode`, and boundary-condition classes.
- `enums.py`: component, port, edge, closure, and boundary enums.
- `flow_source.py`, `pressure_control.py`, `plugflow.py`, `junction.py`, `valve.py`, `vessel.py`: reusable component patterns.
- `command.py`: command result objects used by controllable components.
- `components/__init__.py`: public exports for component classes.

Figure-specific or catalog-specific variants live under `src/chemunited_core/figure_registry/`.

Important files:

- `figure_registry/__init__.py`: maps component figure names to `(DataClass, ModeClass)`.
- `pipes.py`, `pumps.py`, `controllers.py`, `vessels.py`, `rotary_valve.py`, `solenoid_valve.py`, `thermal.py`, `technical.py`, `assemble.py`: concrete component variants used by the catalog.

## The Short Checklist

1. Decide whether you can subclass an existing component pattern.
2. Create a `*Mode` class if the component has configurable fields.
3. Create a dataclass `*Data` class with matching runtime fields.
4. Override `internal_structure()` to populate `port_pairs`, `ports_by_number`, `internal_edges`, and `internal_inventories`.
5. Override `sync_internal_state()` when any configurable field affects derived runtime state.
6. Override `put()` and `apply()` only for commandable components.
7. Export the class from `components/__init__.py` if it is a reusable core component.
8. Register the visible catalog figure in `figure_registry/__init__.py`.
9. Add a small test that builds the component and inspects the compiled topology.

## When to Subclass an Existing Pattern

Prefer subclassing an existing `*Data` class if your new component has the same topology.

Use these base patterns:

- Terminal fixed flow: `FlowSourceMode` / `FlowSourceData`.
- Terminal fixed pressure: `PressureControlMode` / `PressureControlData`.
- Tube, loop, reactor channel: `PlugFlowMode` / `PlugFlowComponentData`.
- Splitter or combiner: `JunctionMode` / `JunctionData`.
- Rotary or switching valve: `ValveMode` / `ValveComponentData`.
- Vessel, vial, bottle, flask, inventory holder: `VesselMode` / `VesselComponentData`.
- Passive non-hydraulic widget: `NeutralComponentData`.

For example, `SyringePumpData` subclasses `FlowSourceData` because its runtime topology is still a single fixed-flow boundary. It only adds `put()` / `apply()` command behavior.

## `ComponentMode`: User-Editable Configuration

`ComponentMode` is a Pydantic model. The GUI and config system read its fields and metadata.

Base attributes:

- `name: str`
  Unique component name in the orchestration. The validator rejects `.` and `_`, because port and edge names use those characters as separators.

- `figure: str`
  Catalog or figure class name. This is the key used by `figure_registry.COMPONENTS`.

- `position: tuple[float, float]`
  Scene position for GUI rendering. It is hidden from normal property editing.

- `angle: int`
  Rotation angle in degrees from `0` to `360`.

- `mirror: bool`
  Whether the GUI should horizontally mirror the figure.

Field metadata is placed in `Field(..., json_schema_extra={...})`.

Common metadata keys:

- `group`
  Usually one of `GroupParameterCategory.GENERAL.value`, `PROPERTY.value`, or `STATUS.value`. This tells the GUI where to group the field.

- `visible`
  `False` hides a field from the GUI.

- `editable`
  Whether a field can be edited after component creation.

- `creation_editable`
  Whether a field can be edited while the component is being created.

- `lock_reason`
  Human-readable reason a field is locked.

- `on_text` / `off_text`
  Labels for boolean switches.

- `Options`
  Option labels for constrained string values.

For unit-aware fields, use `ChemUnitQuantity` with `ChemQuantityValidator`.

```python
from typing import Annotated

from pydantic import Field

from chemunited_core.common.enums import GroupParameterCategory
from chemunited_core.components import ComponentMode
from chemunited_core.utils.internal_quantity import (
    ChemQuantityValidator,
    ChemUnitQuantity,
)


class ExampleTubeMode(ComponentMode):
    length: Annotated[ChemUnitQuantity, ChemQuantityValidator("mm")] = Field(
        default=ChemUnitQuantity("100 mm"),
        title="Length",
        description="Internal channel length.",
        json_schema_extra={"group": GroupParameterCategory.PROPERTY.value},
    )
```

Important rule: every user-facing value that must survive serialization should be declared on the `*Mode` class.

## `ComponentData`: Runtime Structure

`ComponentData` is a dataclass. It is built from a matching mode by `Element.from_mode(mode)`.

Base attributes:

- `name: str`
  Same meaning as `ComponentMode.name`.

- `figure: str`
  Same meaning as `ComponentMode.figure`.

- `position: tuple[float, float]`
  GUI position.

- `angle: int`
  GUI rotation.

- `mirror: bool`
  GUI mirror flag.

- `COMPONENT_TYPE: ClassVar[ComponentType]`
  Class-level classification. Use `ComponentType.UTENSIL` for passive equipment and `ComponentType.ELECTRONIC` for electronically controlled devices.

- `port_pairs: list[tuple[int, ...]]`
  Valid external connection groupings. For a two-port inline element use `[(1, 2)]`. For a terminal element use `[(1,)]`. For a junction with a hidden hub, use pairs such as `[(1, 0), (2, 0), (3, 0)]`.

- `ports_by_number: dict[int, Port]`
  All ports indexed by port number.

- `internal_edges: dict[tuple[int | str, int | str], InternalEdge]`
  Internal channels keyed by `(origin_endpoint, destination_endpoint)`.

- `internal_inventories: dict[str, InventoryNode]`
  Lumped storage nodes. Vessels usually use the stable key `"Inventory"`.

Properties:

- `component_type`
  Returns `type(self).COMPONENT_TYPE`.

- `is_electronic`
  `True` if `COMPONENT_TYPE` is `ComponentType.ELECTRONIC`.

- `internal_inventory`
  Compatibility alias for the first inventory node. New code should prefer `internal_inventories`.

Lifecycle methods:

- `__post_init__()`
  Automatically calls `internal_structure()` after dataclass construction.

- `internal_structure()`
  Must populate ports, internal edges, inventories, and valid port pairs.

- `sync_internal_state()`
  Refreshes derived runtime state after `update()` or `apply()` changes parameters.

- `put(command, **kwargs)`
  Pure validation or planning for a command. It should not mutate the component.

- `apply(command, **kwargs)`
  Mutates live runtime state and returns `PutResult`. Call `sync_internal_state()` here whenever a command changes fields that affect topology, boundaries, or edge state.

## Internals Glossary

Internals live in `chemunited_core.components.internals`.

### `PortBoundaryCondition`

Represents a solver constraint at a port.

Attributes:

- `kind: BoundaryConditionKind`
  `NONE`, `PRESSURE`, or `FLOW`.

- `value: float`
  SI value. Use Pascals for pressure and cubic metres per second for flow.

Use it for terminal source/sink-like components. Leave `Port.boundary` as `None` for ordinary internal network ports.

### `Port`

Represents a physical connection point.

Attributes:

- `number: int`
  Unique port number inside the component. `0` is allowed for internal hub ports.

- `component: str`
  Owning component name.

- `category: ConnectionType`
  Connection class: `HYDRAULIC`, `HEAT`, `ELECTRONIC`, or `MOVEMENT`.

- `relative_position: tuple[float, float]`
  GUI offset from the component center.

- `access: PortAccess`
  Physical access side, currently `TOP` or `BOTTOM`. Vessels use this to distinguish gas-side and liquid-side access.

- `closure: PortClosure`
  `OPEN` or `CAPPED`. A capped port represents a physically sealed connection.

- `boundary: PortBoundaryCondition | None`
  Optional fixed pressure or fixed flow constraint.

- `is_hub: bool`
  Marks a port as an internal hub/staging node. Pumps and distribution valves use this.

- `show_in_graph: bool`
  Whether the GUI should render the port. Hidden hub ports usually set this to `False`.

Useful helpers:

- `port.name`
  Returns `"<component>.<number>"`.

- `port.block(True)`
  Caps the port.

- `port.block(False)`
  Opens the port.

### `InternalEdge`

Represents a directed internal hydraulic path.

Attributes:

- `origin_port: int | str`
  Start endpoint. Usually a port number. May also be an inventory key such as `"Inventory"`.

- `destination_port: int | str`
  End endpoint. Usually a port number or inventory key.

- `length: float`
  Internal channel length in metres.

- `diameter: float`
  Internal channel inner diameter in metres.

- `role: InternalEdgeRole`
  `TRANSPORT` means geometry matters. `JUNCTION` means a lossless or near-lossless internal connection.

- `resistance_override: float | None`
  Fixed hydraulic resistance in `Pa*s/m^3`. `None` means the solver computes resistance from geometry.

Useful helpers:

- `edge.is_active`
  `True` when `resistance_override is None`.

- `edge.close()`
  Sets resistance to `R_MAX_HYDRAULIC`.

- `edge.open()`
  Clears the override so resistance is geometry-based.

### `InventoryNode`

Represents lumped storage for vessels, reactors, wells, and similar components.

Attributes:

- `liq_content: VolumeContentBase`
  Initial liquid phase content.

- `gas_content: VolumeContentBase`
  Initial gas phase content.

Vessels normally start with gas volume equal to capacity and liquid volume equal to zero.

## Common Topology Recipes

### Two-Port Inline Transport

Use this for tubing, loops, columns, flow reactors, and any component where geometry determines hydraulic resistance.

```python
self.port_pairs = [(1, 2)]
self.ports_by_number = {
    1: Port(number=1, component=self.name, relative_position=(-25, 0)),
    2: Port(number=2, component=self.name, relative_position=(25, 0)),
}
self.internal_edges = {
    (1, 2): InternalEdge(
        origin_port=1,
        destination_port=2,
        length=self.length_value,
        diameter=self.diameter_value,
    )
}
self.internal_inventories = {}
```

### Terminal Fixed-Flow Component

Use this for flow sources.

```python
self.port_pairs = [(1,)]
self.ports_by_number = {
    1: Port(
        number=1,
        component=self.name,
        boundary=PortBoundaryCondition(
            kind=BoundaryConditionKind.FLOW,
            value=self.flow_rate_si,
        ),
    )
}
self.internal_edges = {}
self.internal_inventories = {}
```

### Terminal Fixed-Pressure Component

Use this for pressure sources or pressure controllers.

```python
self.port_pairs = [(1,)]
self.ports_by_number = {
    1: Port(
        number=1,
        component=self.name,
        boundary=PortBoundaryCondition(
            kind=BoundaryConditionKind.PRESSURE,
            value=self.setpoint_pa,
        ),
    )
}
self.internal_edges = {}
self.internal_inventories = {}
```

### Junction With Hidden Hub

Use this for splitters and combiners.

```python
self.port_pairs = [(1, 0), (2, 0), (3, 0)]
self.ports_by_number = {
    0: Port(number=0, component=self.name, show_in_graph=False),
    1: Port(number=1, component=self.name),
    2: Port(number=2, component=self.name),
    3: Port(number=3, component=self.name),
}
self.internal_edges = {
    (1, 0): InternalEdge(1, 0, role=InternalEdgeRole.JUNCTION),
    (2, 0): InternalEdge(2, 0, role=InternalEdgeRole.JUNCTION),
    (3, 0): InternalEdge(3, 0, role=InternalEdgeRole.JUNCTION),
}
self.internal_inventories = {}
```

### Vessel With Inventory

Use this for flasks, bottles, vials, wells, and storage containers.

```python
self.port_pairs = [(1,), (2,)]
self.ports_by_number = {
    1: Port(number=1, component=self.name, access=PortAccess.TOP),
    2: Port(number=2, component=self.name, access=PortAccess.BOTTOM),
}
self.internal_edges = {
    (1, DEFAULT_INVENTORY_KEY): InternalEdge(
        origin_port=1,
        destination_port=DEFAULT_INVENTORY_KEY,
        role=InternalEdgeRole.JUNCTION,
    ),
    (2, DEFAULT_INVENTORY_KEY): InternalEdge(
        origin_port=2,
        destination_port=DEFAULT_INVENTORY_KEY,
        role=InternalEdgeRole.JUNCTION,
    ),
}
self.internal_inventories = {
    DEFAULT_INVENTORY_KEY: InventoryNode(
        gas_content=VolumeContentBase(volume=self.capacity_value),
        liq_content=VolumeContentBase(volume=0, phase_kind=PhaseKind.LIQUID),
    )
}
```

### Switchable Edge

Use this for valves, regulators, and flow controllers.

```python
self.internal_edges = {
    (1, 2): InternalEdge(origin_port=1, destination_port=2).close()
}

# Later, in sync_internal_state() or apply():
self.internal_edges[(1, 2)].open()
self.internal_edges[(1, 2)].close()
```

## Full Simple Example: UV Flow Cell

This example creates a two-port inline component with a channel length, channel diameter, and one electronic signal port. It behaves like a plug-flow component hydraulically, but it also exposes an electronic connection.

Create `src/chemunited_core/components/uv_flow_cell.py`:

```python
from dataclasses import dataclass
from typing import Annotated, ClassVar

from pydantic import Field
from typing_extensions import override

from chemunited_core.common.enums import ConnectionType, GroupParameterCategory
from chemunited_core.components.component import ComponentData, ComponentMode
from chemunited_core.components.enums import ComponentType
from chemunited_core.components.internals import InternalEdge, Port
from chemunited_core.utils.internal_quantity import (
    ChemQuantityValidator,
    ChemUnitQuantity,
)


class UVFlowCellMode(ComponentMode):
    length: Annotated[ChemUnitQuantity, ChemQuantityValidator("mm")] = Field(
        default=ChemUnitQuantity("20 mm"),
        title="Channel Length",
        description="Hydraulic path length through the flow cell.",
        json_schema_extra={"group": GroupParameterCategory.PROPERTY.value},
    )
    diameter: Annotated[ChemUnitQuantity, ChemQuantityValidator("mm")] = Field(
        default=ChemUnitQuantity("0.5 mm"),
        title="Channel Diameter",
        description="Inner hydraulic diameter of the flow cell.",
        json_schema_extra={"group": GroupParameterCategory.PROPERTY.value},
    )
    wavelength: int = Field(
        default=254,
        ge=190,
        le=800,
        title="Wavelength",
        description="Detector wavelength in nm.",
        json_schema_extra={"group": GroupParameterCategory.STATUS.value},
    )


@dataclass
class UVFlowCellData(ComponentData):
    COMPONENT_TYPE: ClassVar[ComponentType] = ComponentType.ELECTRONIC

    length: ChemUnitQuantity = ChemUnitQuantity("20 mm")
    diameter: ChemUnitQuantity = ChemUnitQuantity("0.5 mm")
    wavelength: int = 254

    @property
    def length_value(self) -> float:
        return self.length.to_base_units().magnitude

    @property
    def diameter_value(self) -> float:
        return self.diameter.to_base_units().magnitude

    @override
    def internal_structure(self) -> None:
        self.port_pairs = [(1, 2), (3,)]
        self.ports_by_number = {
            1: Port(number=1, component=self.name, relative_position=(-25, 0)),
            2: Port(number=2, component=self.name, relative_position=(25, 0)),
            3: Port(
                number=3,
                component=self.name,
                category=ConnectionType.ELECTRONIC,
                relative_position=(0, -25),
            ),
        }
        self.internal_edges = {
            (1, 2): InternalEdge(
                origin_port=1,
                destination_port=2,
                length=self.length_value,
                diameter=self.diameter_value,
            )
        }
        self.internal_inventories = {}

    @override
    def sync_internal_state(self) -> None:
        edge = self.internal_edges[(1, 2)]
        edge.length = self.length_value
        edge.diameter = self.diameter_value
```

Then export it from `src/chemunited_core/components/__init__.py`:

```python
from .uv_flow_cell import UVFlowCellData, UVFlowCellMode

__all__ = [
    # ...
    "UVFlowCellData",
    "UVFlowCellMode",
]
```

Then register a catalog figure in `src/chemunited_core/figure_registry/__init__.py`:

```python
from chemunited_core.components import UVFlowCellData, UVFlowCellMode

COMPONENTS: dict[str, tuple[type[ComponentData], type[ComponentMode]]] = {
    # ...
    "UVFlowCell": (UVFlowCellData, UVFlowCellMode),
}
```

Build and inspect it:

```python
from chemunited_core.components import UVFlowCellData, UVFlowCellMode

mode = UVFlowCellMode(
    name="UVDetector",
    figure="UVFlowCell",
    length="30 mm",
    diameter="0.75 mm",
    wavelength=280,
)

data = UVFlowCellData.from_mode(mode)

assert sorted(data.ports_by_number) == [1, 2, 3]
assert data.port_pairs == [(1, 2), (3,)]
assert data.internal_edges[(1, 2)].length == data.length_value
```

Update it:

```python
data.update(UVFlowCellMode(length="50 mm"))

assert data.internal_edges[(1, 2)].length == data.length_value
```

## Commandable Components

Use commands when the component changes during a running protocol.

`put()` should validate or calculate scheduled follow-up commands without mutating state.

`apply()` should mutate the live dataclass and call `sync_internal_state()` when needed.

Example:

```python
from chemunited_core.components import PutResult
from chemunited_core.utils.internal_quantity import ChemUnitQuantity


def apply(self, command: str, **kwargs) -> PutResult:
    if command == "set":
        self.flow_rate = ChemUnitQuantity(kwargs["rate"])
        self.sync_internal_state()
    return PutResult()
```

Use `ScheduledCommand` when a command should trigger a later command, such as stopping a syringe pump after a requested volume:

```python
from chemunited_core.components import PutResult, ScheduledCommand

return PutResult(
    scheduled=[
        ScheduledCommand(dt=seconds_until_stop, command="stop"),
    ]
)
```

## Attribute Rules and Pitfalls

- Keep field names identical between `*Mode` and `*Data` when `from_mode()` should copy them.
- Use dataclass `field(default_factory=...)` for mutable defaults such as lists or layout structures.
- Always set `self.internal_inventories = {}` for components without storage.
- Always set `self.internal_edges = {}` for components without internal hydraulic paths.
- Use SI floats in runtime internals: metres, cubic metres per second, Pascals.
- Keep user input unit-aware by accepting strings through `ChemUnitQuantity` fields.
- Use `sync_internal_state()` for derived state rather than rebuilding the whole component unless topology itself changes.
- If a creation-time field changes port count or topology, mark it with `editable=False` and `creation_editable=True`.
- Use `show_in_graph=False` for hidden hub ports.
- Use `ConnectionType.HEAT`, `ELECTRONIC`, or `MOVEMENT` for non-hydraulic ports.
- Use `InternalEdgeRole.JUNCTION` for hub or inventory links.
- Use `InternalEdgeRole.TRANSPORT` for physical channels where geometry matters.
- Use `.close()` / `.open()` instead of manually assigning large resistance values.
- Use `ComponentType.ELECTRONIC` for components controlled by protocol commands or electronic managers.
- Use `ComponentType.UTENSIL` for passive physical equipment.

## Minimal Test Template

Add a focused test when the component is new:

```python
from chemunited_core.components import UVFlowCellData, UVFlowCellMode


def test_uv_flow_cell_topology() -> None:
    data = UVFlowCellData.from_mode(
        UVFlowCellMode(name="UVDetector", figure="UVFlowCell")
    )

    assert data.figure == "UVFlowCell"
    assert data.port_pairs == [(1, 2), (3,)]
    assert set(data.ports_by_number) == {1, 2, 3}
    assert set(data.internal_edges) == {(1, 2)}
    assert data.internal_inventories == {}
```

Run:

```bash
python -m pytest
pre-commit run --all-files
```

## Choosing the Right Internal Shape

Ask this first: what graph should the simulator see?

- One terminal node that fixes flow: single `Port` with `BoundaryConditionKind.FLOW`.
- One terminal node that fixes pressure: single `Port` with `BoundaryConditionKind.PRESSURE`.
- A physical channel: two ports and one `TRANSPORT` `InternalEdge`.
- A splitter/combiner: visible ports plus a hidden hub port with `JUNCTION` edges.
- A storage object: visible ports connected to an `InventoryNode`.
- A switch: all possible edges exist, inactive ones are closed with `edge.close()`.
- A visual-only or non-hydraulic object: `NeutralComponentData` with heat, electronic, movement, or no ports.

Once that graph is correct, the `Mode` fields, figure registry entry, command methods, and tests are usually straightforward.
