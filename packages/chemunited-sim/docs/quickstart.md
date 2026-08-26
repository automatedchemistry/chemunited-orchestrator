# Quickstart

This page shows the shortest path from a clean checkout to a working
simulation.

## Install

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
```

This installs `chemunited-sim` in editable mode and pulls `chemunited-core`
directly from GitHub.

For tests and formatting tools:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

## Run A Minimal Hydraulic Platform

The example below builds a pressure source, a plug-flow tube, and a pressure
sink. It compiles the platform, runs one second of simulation, and records
pressures and flows to SQLite.

```python
from pathlib import Path

from chemunited_core.common.enums import ConnectionType
from chemunited_core.components import (
    PlugFlowComponentData,
    PlugFlowMode,
    PressureControlData,
    PressureControlMode,
)
from chemunited_core.connections import EdgeData, EdgeMode
from chemunited_core.utils.internal_quantity import ChemUnitQuantity

from chemunited_sim.adapter import compile_graph
from chemunited_sim.recorder import Recorder
from chemunited_sim.worker import SimConfig, Worker


src = PressureControlData.from_mode(
    PressureControlMode(name="src", setpoint=ChemUnitQuantity("2 bar"))
)
tube = PlugFlowComponentData.from_mode(
    PlugFlowMode(
        name="tube",
        length=ChemUnitQuantity("10 cm"),
        diameter=ChemUnitQuantity("4 mm"),
    )
)
snk = PressureControlData.from_mode(
    PressureControlMode(name="snk", setpoint=ChemUnitQuantity("1 bar"))
)

e_in = EdgeData.from_mode(
    EdgeMode(
        name="e_in",
        origin="src",
        origin_port=1,
        destination="tube",
        destination_port=1,
        classification=ConnectionType.HYDRAULIC,
        length=ChemUnitQuantity("5 cm"),
        diameter=ChemUnitQuantity("4 mm"),
    )
)
e_out = EdgeData.from_mode(
    EdgeMode(
        name="e_out",
        origin="tube",
        origin_port=2,
        destination="snk",
        destination_port=1,
        classification=ConnectionType.HYDRAULIC,
        length=ChemUnitQuantity("5 cm"),
        diameter=ChemUnitQuantity("4 mm"),
    )
)

components = [src, tube, snk]
edges = [e_in, e_out]
graph = compile_graph(components, edges)

db_path = Path("simulation.db")
recorder = Recorder(db_path=db_path, graph=graph, dt=0.1, record_interval=0.5)

worker = Worker(
    graph=graph,
    components=components,
    config=SimConfig(dt=0.1, t_end=1.0),
    recorder=recorder,
)
worker.run()

print(f"finished at t={worker.t:.2f} s")
print(worker.hyd_state.pressures)
print(worker.hyd_state.flows)
print(f"recorded to {db_path}")
```

## Run The Included Full Example

```powershell
.\.venv\Scripts\python.exe examples\full_platform.py
```

The full example includes gas and liquid phases, a pressurised reactor, a
back-pressure regulator, a valve switch, a first-order reaction, and SQLite
recording.

## Verify The Package

```powershell
.\.venv\Scripts\pytest.exe
```
