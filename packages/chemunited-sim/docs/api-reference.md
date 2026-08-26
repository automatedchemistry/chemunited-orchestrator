# API Reference

This reference lists the public API exported by each subpackage. For behavior
details, read the source docstrings; the package is intentionally small and the
module boundaries are clear.

## `chemunited_sim.adapter`

```python
from chemunited_sim.adapter import (
    HydraulicEdge,
    HydraulicGraph,
    HydraulicNode,
    compile_graph,
)
```

| Name | Purpose |
|---|---|
| `compile_graph(components, edges)` | Compile `chemunited-core` components and connections into a `HydraulicGraph` |
| `HydraulicNode` | Flat node model for component ports, inventory nodes, and hub nodes |
| `HydraulicEdge` | Directed hydraulic edge with geometry, role, and optional resistance override |
| `HydraulicGraph` | Container for nodes, edges, inventory snapshots, and BPR edge IDs |

Typical use:

```python
graph = compile_graph(components, edges)
```

## `chemunited_sim.hydraulics`

```python
from chemunited_sim.hydraulics import HydraulicSolveError, HydraulicState, solve
```

| Name | Purpose |
|---|---|
| `solve(graph, viscosity=...)` | Solve absolute pressures and signed volumetric flows |
| `HydraulicState` | Immutable snapshot with `pressures` and `flows` dictionaries |
| `HydraulicSolveError` | Raised for invalid edge geometry or unsolved systems |

Flow sign convention: positive means `edge.origin_node_id` to
`edge.destination_node_id`.

## `chemunited_sim.transport`

```python
from chemunited_sim.transport import (
    Pocket,
    TransportResult,
    TransportState,
    advance,
    build_initial_state,
    inject,
)
```

| Name | Purpose |
|---|---|
| `Pocket` | Immutable fluid parcel with phase, volume, species, temperature, and pressure |
| `TransportState` | FIFO pocket queues keyed by edge ID |
| `TransportResult` | Output of `advance`: next state, inventory arrivals, inventory departures |
| `build_initial_state(graph)` | Fill transport edges with initial air pockets |
| `advance(graph, hyd_state, transport_state, dt)` | Move pockets by `abs(flow) * dt` |
| `inject(state, emitted, hyd_state)` | Insert inventory-emitted pockets at edge inflow ends |

## `chemunited_sim.inventory`

```python
from chemunited_sim.inventory import (
    EdgePortAccess,
    InventoryState,
    PortAccessMap,
    assimilate,
    build_inventory_states,
    build_port_map,
    emit,
)
```

| Name | Purpose |
|---|---|
| `InventoryState` | Mutable runtime state for one vessel inventory |
| `build_inventory_states(graph)` | Seed inventory states from graph inventory snapshots |
| `build_port_map(graph, components)` | Map inventory-connected edges to top/bottom port access |
| `assimilate(states, arrivals, hyd_state)` | Absorb arriving pockets into inventories |
| `emit(states, departures, port_map)` | Draw replacement gas/liquid pockets from inventories |
| `EdgePortAccess` | Per-edge record of inventory node and port access |
| `PortAccessMap` | Alias for the edge-to-access mapping |

## `chemunited_sim.reactions`

```python
from chemunited_sim.reactions import (
    FirstOrderDecay,
    NullReaction,
    PhaseReaction,
    Reaction,
    ReactionsMap,
    StoichiometricReaction,
    apply,
    apply_transport,
)
```

| Name | Purpose |
|---|---|
| `Reaction` | Protocol for objects with `step(state, dt) -> None` |
| `PhaseReaction` | Protocol for reactions that can update one transported fluid phase |
| `ReactionsMap` | Reactions keyed by inventory-node ID or transport-edge ID |
| `NullReaction` | No-op reaction |
| `FirstOrderDecay` | Irreversible first-order `A -> B` reaction in one phase |
| `StoichiometricReaction` | Multi-species stoichiometric reaction driven by one controlling species |
| `apply(states, reactions_map, dt)` | Apply all reactions to matching inventory states |
| `apply_transport(state, reactions_map, dt)` | Apply all reactions to resident pockets on matching transport edges |

Example:

```python
from chemunited_core.common.enums import PhaseKind
from chemunited_sim.reactions import FirstOrderDecay

reactions_map = {
    "reactor.Inventory": [
        FirstOrderDecay(
            reactant="reagent_a",
            product="product_b",
            rate_constant=0.05,
            phase=PhaseKind.LIQUID,
        )
    ]
}
```

PlatformBuilder.add_reaction accepts semantic component names. Vessel targets
resolve to the component's Inventory node. FlowReactor and PhotoReactor
targets resolve to their internal 1-to-2 transport edge, where every resident
pocket reacts once per simulation step before transport advances.

## `chemunited_sim.recorder`

```python
from chemunited_sim.recorder import (
    CellDefinition,
    Recorder,
    RecorderWriteError,
    build_cell_definitions,
)
```

| Name | Purpose |
|---|---|
| `Recorder(db_path, graph, dt, ...)` | SQLite writer for simulation snapshots |
| `Recorder.should_record(t)` | Return whether `t` falls on a record interval |
| `Recorder.record(t, hyd_state, transport_state, inv_states)` | Write one snapshot if due |
| `Recorder.close()` | Close the database connection; safe to call repeatedly |
| `RecorderWriteError` | Raised if a write fails |
| `build_cell_definitions(graph, cell_length_m=...)` | Slice transport edges into recorder cells |
| `CellDefinition` | Static cell metadata for spatial recording |

## `chemunited_sim.worker`

```python
from chemunited_sim.worker import SimConfig, Worker
```

| Name | Purpose |
|---|---|
| `SimConfig(dt, t_end, viscosity=..., bpr_max_iters=20)` | Time-step and solver configuration |
| `Worker(graph, components, config, reactions_map=None, recorder=None)` | Main simulation orchestrator |
| `Worker.step()` | Execute one time step |
| `Worker.run()` | Step from current time through `t_end` and close the recorder |
| `Worker.t` | Current simulation time in seconds |
| `Worker.hyd_state` | Most recent hydraulic solve result, or `None` before the first step |
| `Worker.transport_state` | Current pocket queues |
| `Worker.inv_states` | Current inventory states |
