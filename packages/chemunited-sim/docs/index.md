# chemunited-sim Documentation

`chemunited-sim` is the simulation kernel for ChemUnited-style fluidic
automation platforms. It is intentionally GUI-free: it accepts live
`chemunited-core` data objects, compiles them into a simulation graph, runs the
time-step loop, and optionally writes SQLite output for later inspection.

## What The Package Does

At a high level, the package provides:

| Area | Module | Responsibility |
|---|---|---|
| Adapter | `chemunited_sim.adapter` | Compile `ComponentData` and `EdgeData` into a `HydraulicGraph` |
| Hydraulics | `chemunited_sim.hydraulics` | Solve node pressures and signed edge flows |
| Transport | `chemunited_sim.transport` | Move FIFO pockets along transport edges |
| Inventory | `chemunited_sim.inventory` | Assimilate arrivals into vessels and emit replacement pockets |
| Reactions | `chemunited_sim.reactions` | Apply built-in or custom reaction models in vessel inventories |
| Recorder | `chemunited_sim.recorder` | Persist simulation state to SQLite |
| Worker | `chemunited_sim.worker` | Orchestrate one complete operator-splitting simulation loop |

## Read Next

- [Quickstart](quickstart.md): install the package and run a small platform.
- [Architecture](architecture.md): understand the graph model and time-step order.
- [API Reference](api-reference.md): public imports and common call patterns.
- [Recording](recording.md): SQLite output schema and recorder usage.
- [Examples](examples.md): the included full-platform demonstration.
- [MCP Tools](mcp-tools.md): drive the simulation server from an LLM agent.

## Core Conventions

- All internal geometry and physical values are SI units.
- Pressure is absolute pressure in Pa.
- Flow is volumetric flow in m3/s.
- Positive edge flow means origin node to destination node.
- Transport edges hold ordered `Pocket` queues.
- The `Worker` records at the current time before advancing transport, so
  `t=0` is captured when a recorder is attached.
