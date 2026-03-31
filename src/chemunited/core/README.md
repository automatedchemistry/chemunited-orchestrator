# chemunited-core

Core data models for orchestration, execution, and simulation of automated chemistry platforms.

`chemunited-core` is the shared schema and runtime-model layer for the ChemUnited stack. It gives downstream packages a consistent way to describe equipment, inter-component connections, internal topology, and unit-aware physical quantities.

## Installation

Requires Python `>=3.11`.

```bash
pip install chemunited-core
```

For local development:

```bash
pip install -e ".[dev]"
```

## Architecture

The editable architecture diagram lives at [docs/chemunited-core-architecture.drawio](docs/chemunited-core-architecture.drawio).

The package follows one core pattern everywhere:

```text
Pydantic *Mode -> Element.from_mode(...) -> dataclass *Data -> consumer package
                                   |
                                   +-> Element.update(...) -> sync_internal_state()
```

- `*Mode` classes validate config, UI, or protocol input.
- `*Data` classes hold the runtime representation used by orchestration, visualization, or simulation layers.
- `Element.from_mode(mode)` builds fully initialized dataclass instances.
- `Element.update(mode)` applies only explicitly provided fields, then refreshes derived runtime state through `sync_internal_state()`.

## Public API

Import public symbols from subpackages such as `chemunited_core.components` and `chemunited_core.connections`. There is currently no single top-level export module intended to be the main public surface.

| Module | Purpose | Main public objects |
| --- | --- | --- |
| `chemunited_core.components` | Process equipment models | `ComponentMode`, `ComponentData`, `FlowSourceMode`, `FlowSourceData`, `JunctionMode`, `JunctionData`, `PlugFlowMode`, `PlugFlowComponentData`, `PressureControlMode`, `PressureControlData`, `BackPressureRegulatorMode`, `BackPressureRegulatorData`, `ValveMode`, `ValveComponentData`, `VesselMode`, `VesselComponentData` |
| `chemunited_core.connections` | Inter-component edges | `EdgeMode`, `EdgeData`, `ConnectionType` |
| `chemunited_core.common` | Shared enums and mode-to-data bridge | `Element`, `ConnectionType`, `GroupParameterCategory` |
| `chemunited_core.utils` | Unit-aware physical quantities | `ChemUnitQuantity`, `ChemQuantityValidator`, `ureg` |
| `chemunited_core.compounds` | Inventory payload objects | `VolumeContentBase` |

## Component Catalog

| Model pair | Role | Runtime topology |
| --- | --- | --- |
| `ComponentMode` / `ComponentData` | Base component contract | Two hydraulic ports by default, no inventory |
| `FlowSourceMode` / `FlowSourceData` | Fixed-flow boundary | One hydraulic port with a `FLOW` boundary condition |
| `PressureControlMode` / `PressureControlData` | Fixed-pressure boundary | One hydraulic port with a `PRESSURE` boundary condition |
| `PlugFlowMode` / `PlugFlowComponentData` | Tube or reactor channel | Two hydraulic ports joined by one transport edge |
| `JunctionMode` / `JunctionData` | Splitter or combiner | N external ports connected to hub port `0` through junction edges |
| `ValveMode` / `ValveComponentData` | Rotary switching element | All possible internal routes are compiled; only active routes stay open |
| `BackPressureRegulatorMode` / `BackPressureRegulatorData` | Pressure-controlled inline valve | Two ports joined by a normally closed internal edge |
| `VesselMode` / `VesselComponentData` | Storage and phase inventory | Top and bottom hydraulic ports plus one heat port and one inventory node |

## Consumer Contract

Another package can safely rely on the following behavior:

- `Element.from_mode(mode)` accepts a Pydantic model and returns the matching dataclass with derived runtime fields already built.
- `Element.update(mode)` patches only fields explicitly set on the incoming mode object and then calls `sync_internal_state()`.
- Every `ComponentData` instance exposes `name`, `figure`, `position`, `angle`, `component_type`, `port_pairs`, `ports_by_number`, `internal_edges`, and `internal_inventory`.
- `ports_by_number` contains `Port` objects with stable fields such as `number`, `component`, `category`, `relative_position`, `access`, `closure`, and optional `boundary`.
- `internal_edges` contains `InternalEdge` objects keyed by `(origin_port, destination_port)` or `(origin_port, "Inventory")`.
- `internal_inventory` is either `None` or an `InventoryNode` that stores `liq_content` and `gas_content`.
- `EdgeData` exposes `origin`, `destination`, `origin_port`, `destination_port`, `classification`, `length`, `diameter`, `straight_path`, and `air_pressure_line`.
- `EdgeData.name` is a stable identifier in the form `<origin>_<origin_port>_<destination>_<destination_port>`.
- `ChemUnitQuantity` stores unit-aware values. Use `.to_base_units().magnitude` when your consumer needs SI floats.
- Non-hydraulic `EdgeMode` classifications normalize `length` and `diameter` to `0 mm`.
- `EdgeMode` accepts `destiny` and `destiny_port` as aliases for backward compatibility.

## Using It From Another Package

Create validated `*Mode` objects, compile them to `*Data`, then read the runtime topology.

```python
from chemunited_core.components import (
    FlowSourceData,
    FlowSourceMode,
    PlugFlowComponentData,
    PlugFlowMode,
    VesselComponentData,
    VesselMode,
)
from chemunited_core.connections import EdgeData, EdgeMode

source = FlowSourceData.from_mode(
    FlowSourceMode(
        name="FeedPump",
        figure="PumpFigure",
        position=(0.0, 0.0),
        angle=0,
        flow_rate="5 ml/min",
    )
)

reactor = PlugFlowComponentData.from_mode(
    PlugFlowMode(
        name="ReactorTube",
        figure="TubeFigure",
        position=(2.0, 0.0),
        angle=0,
        length="500 mm",
        diameter="2 mm",
    )
)

receiver = VesselComponentData.from_mode(
    VesselMode(
        name="Receiver",
        figure="FlaskFigure",
        position=(4.0, 0.0),
        angle=0,
        capacity="250 ml",
        top_access=3,
        bottom_access=2,
    )
)

edge_a = EdgeData.from_mode(
    EdgeMode(
        origin=source.name,
        destination=reactor.name,
        origin_port=1,
        destination_port=1,
        length="100 mm",
        diameter="1.6 mm",
    )
)

edge_b = EdgeData.from_mode(
    EdgeMode(
        origin=reactor.name,
        destination=receiver.name,
        origin_port=2,
        destination_port=1,
        length="150 mm",
        diameter="1.6 mm",
    )
)

components = [source, reactor, receiver]
connections = [edge_a, edge_b]
```

Inspect the compiled topology through public runtime fields:

```python
for component in components:
    print(component.name, sorted(component.ports_by_number))
    print(component.port_pairs)
    print(component.internal_inventory)

for edge_key, internal_edge in reactor.internal_edges.items():
    print(edge_key, internal_edge.length, internal_edge.diameter)
```

Apply updates through `update()` so derived state stays in sync:

```python
source.update(FlowSourceMode(flow_rate="8 ml/min"))
reactor.update(PlugFlowMode(length="750 mm", diameter="1.0 mm"))
```

That patch-style update behavior is especially useful when another package stores partial UI edits, protocol commands, or configuration diffs.

## Ports, Internal Edges, and Inventory

For downstream packages, the most important compiled objects are:

- `Port`: the externally connectable point on a component. GUI or graph packages usually read `relative_position`, `category`, `access`, `closure`, and `boundary`.
- `InternalEdge`: the directed edge inside a component. Simulation packages usually read `length`, `diameter`, `role`, and `resistance_override`.
- `InventoryNode`: the lumped storage node for vessels and similar components.

These objects live in `chemunited_core.components.internals` and are populated by each component's `internal_structure()` implementation.

## Units and Quantities

`chemunited-core` uses Pint-backed quantities through `ChemUnitQuantity`.

- Mode fields accept strings such as `"5 ml/min"`, `"250 ml"`, `"1.2 bar"`, or `"500 mm"`.
- Runtime helpers such as `flow_rate_si`, `setpoint_pa`, `length_value`, `diameter_value`, and `capacity_value` expose SI magnitudes where needed.
- Shared unit conversions should use `chemunited_core.utils.ureg`.

## Examples

See [examples/build_valve_graph.py](examples/build_valve_graph.py) for a runnable example that builds a small hydraulic setup and inspects component ports, internal edges, and process connections.

Run it from the repository root:

```bash
python examples/build_valve_graph.py
```

If `pyvis` is installed, the example also writes an HTML graph to `examples/output/valve_flow_graph.html`.

## Development

The current verified quality gate is:

```bash
pre-commit run --all-files
```

Useful local checks:

```bash
python -c "import sys; from pathlib import Path; sys.path.insert(0, str(Path('src').resolve())); import chemunited_core.components"
python examples/build_valve_graph.py
```

The `tests/` directory exists, but there are currently no checked-in test modules.

## License

See [LICENSE](LICENSE).
