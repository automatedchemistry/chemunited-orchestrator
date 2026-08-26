# Recording

The recorder writes simulation snapshots to SQLite. It is optional: simulations
can run without attaching a recorder.

## Basic Usage

```python
from chemunited_sim.recorder import Recorder
from chemunited_sim.worker import Worker

recorder = Recorder(
    db_path="simulation.db",
    graph=graph,
    dt=0.1,
    record_interval=1.0,
    platform_name="demo",
    components=components,
)

worker = Worker(graph, components, config, recorder=recorder)
worker.run()
```

`Worker.run()` closes the recorder after the last step. If you call
`Worker.step()` manually, close the recorder yourself when finished.

## Recording Times

The recorder uses integer tick arithmetic:

```text
tick = round(t / dt)
should_record = tick % round(record_interval / dt) == 0
```

This avoids common floating-point modulo drift. If `record_interval` is not a
close multiple of `dt`, the recorder emits a warning and rounds to the nearest
tick interval.

The worker records before transport advances, so `t=0` is included.

## Static Tables

Static tables are written once at construction.

| Table | Content |
|---|---|
| `meta` | `dt`, `record_interval`, `platform_name`, and UTC timestamp |
| `edge_cells` | Fixed cell layout for every eligible transport edge |

## Dynamic Tables

Dynamic tables are appended at every record interval.

| Table | Content |
|---|---|
| `node_pressure` | Absolute pressure for every node |
| `edge_flow` | Signed volumetric flow for every edge |
| `inventory_state` | Vessel pressure and temperature |
| `inventory_content` | Phase volume and species moles in vessel inventories |
| `cell_state` | Phase fraction and temperature per transport cell |
| `cell_content` | Species moles per transport cell |
| `component_state` | Discrete component state not recoverable from the other tables |

When a phase has no tracked species, `inventory_content` writes a sentinel
species ID named `__carrier__` with zero moles so readers can still see the
phase volume.

`component_state` covers the small set of discrete (non-continuous) fields
that `ComponentData.apply()` can mutate: a rotary valve's `rotor_ports` and a
solenoid valve's `opened`. One row is written per relevant component per
record interval, with `state` holding a JSON blob (`{"rotor_ports": [...]}`
or `{"opened": true}`) rather than dedicated columns, since `rotor_ports` is
a nested structure that doesn't flatten. Passing `components=` to `Recorder`
is optional — omit it (or a graph with no valve/solenoid components) and no
rows are written.

## Reader Guidance

The recorder owns one write connection for the simulation run. Tools or GUIs
that inspect the database should open a separate read-only connection:

```python
import sqlite3

conn = sqlite3.connect("file:simulation.db?mode=ro", uri=True)
```

The recorder enables WAL mode, so independent readers can inspect the database
while the writer is alive.
