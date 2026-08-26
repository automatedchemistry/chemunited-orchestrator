# Architecture

`chemunited-sim` is split into small domain modules. The modules share a
compiled `HydraulicGraph` and pass explicit state objects between steps.

## Data Flow

```text
chemunited-core components + edges
        |
        v
adapter.compile_graph(...)
        |
        v
HydraulicGraph
        |
        v
Worker.step()
```

The package does not read GUI objects directly during simulation. It consumes
`chemunited-core` component and connection data, compiles a graph, and then
runs from the compiled graph and runtime state. The worker also keeps the
live `ComponentData` instances so active elements (pumps, MFCs, BPRs, flow
sources) can be re-evaluated each tick.

## Worker Step Order

`Worker.step()` applies one operator-splitting time step:

1. Solve hydraulics.
2. Refresh active-element edge state for the *next* solve:
   - Pumps: `comp.sync_forced_flow()` copies `flow_rate` straight onto the
     edge's `forced_flow` override — a hard flow-source constraint, not
     resistance-derived, so it needs no pressure feedback and cannot be
     wrong-signed by back-pressure.
   - MFCs: `comp.update_resistance(dp)` from the edge pressure drop, same as
     before — an MFC is a controlled variable-resistance element (like a
     valve), not a forced-flow source, so it still responds to real
     back-pressure.
   - BPRs: see [Back-Pressure Regulators](#back-pressure-regulators).
3. Record the current state if a `Recorder` is attached and the record
   interval is due.
4. Advance transport pockets through edges.
5. Assimilate arrived pockets into vessel inventories.
6. Apply reactions to inventory states.
7. Apply wall heat exchange (Newton cooling) to vessels that enable it.
8. Emit replacement pockets from inventories for departing volumes.
9. Emit pockets from `FlowSource` boundary components (infinite reservoirs,
   or finite syringe pumps with tracked remaining volume).
10. Inject all emitted pockets into transport queues and pad underfilled
    edges with air carrier pockets.
11. Advance simulation time by `dt`.

Because recording happens before transport advances, a full `Worker.run()`
with a recorder captures `t=0`. `Worker.run()` terminates at
`config.t_end` (integer-tick arithmetic, inclusive) and/or when an optional
`stop_condition` callable returns `True`; at least one of the two must be
provided.

## Hydraulic Graph

The adapter compiles a platform into:

- `HydraulicNode`: an immutable component port, inventory node, or junction
  hub, optionally carrying a boundary condition.
- `HydraulicEdge`: an internal component channel or external connection.
  Mutable — the worker rewrites `resistance_override` in-place each tick for
  MFC, BPR, and valve edges, and `forced_flow` for pump edges.
- `HydraulicGraph`: dictionaries of nodes and edges, plus deep-copied
  `InventoryNode` snapshots used to seed inventory states.

`adapter.resync_component()` re-propagates a component's internal-edge
resistance and forced-flow overrides into the compiled graph after runtime
commands (e.g. valve switches, pump infuse/stop); the compiled topology never
changes. The solver derives active hydraulic connectivity from current
conductances on every solve.

All lengths, diameters, volumes, pressures, flows, temperatures, and
resistances are converted to SI values before simulation modules consume them.

## Hydraulics

`chemunited_sim.hydraulics.solve()` builds a sparse nodal admittance system
and solves for absolute pressure at each node with
`scipy.sparse.linalg.spsolve`. Edge flows are then back-computed as
`Q = G · (P_origin − P_destination)` (signed: positive = origin →
destination).

Boundary handling:

- Pressure boundaries pin a node to an absolute pressure (Dirichlet row
  replacement).
- Flow boundaries add a source/sink term to the right-hand side (Neumann).
- Connected components without pressure boundaries are anchored to
  atmosphere at one node to keep the system non-singular.

Per-edge handling, in priority order:

1. Overrides at or above `R_MAX_HYDRAULIC / 2` are hard-closed before
   anything else. They contribute zero conductance, are excluded from active
   connected-component detection, and report exactly zero flow.
2. `forced_flow` (active pump edges) bypasses resistance entirely: zero
   conductance, but the edge injects its fixed flow directly into the
   right-hand side as a Neumann source/sink pair, so it is exact and
   correctly-signed regardless of the pressure field. Like a hard-closed
   edge, it's excluded from connected-component detection — an ideal pump
   genuinely decouples upstream and downstream absolute pressure.
3. `resistance_override` is used directly when set otherwise — this is how
   MFCs and BPRs are represented.
4. Junction edges use the small epsilon resistance `R_JUNCTION`
   (nearly lossless, keeps the matrix well-conditioned).
5. Transport edges use Hagen-Poiseuille resistance
   `R = 128·η·L / (π·D⁴)` with the configured carrier viscosity.

## Transport

Transport edges hold FIFO queues of immutable `Pocket` objects. A pocket
stores phase, volume, species moles, temperature, and pressure.

Deque orientation is fixed to graph orientation:

- `deque[0]` is closest to the destination node.
- `deque[-1]` is closest to the origin node.
- Positive flow pops from the destination end.
- Negative flow pops from the origin end.

`advance()` performs two passes per step. Pass 1 pops the displaced volume
`|Q|·dt` from each open transport edge (splitting the boundary pocket if
needed) and routes each exiting pocket — following junction edges in the
direction of flow, up to a hop limit — until it reaches:

- an inventory node (added to arrivals),
- a hub node (staged for pass 2),
- another transport edge fed from a port (re-injected, split across outgoing
  edges by displaced volume), or
- a dead-end boundary port (absorbed and discarded).

Pass 2 merges hub-staged pockets by phase (ideal mixing) and redistributes
them to outgoing transport edges proportionally to displaced volume. An
outgoing transport edge may be attached directly to the hub node itself
(e.g. a rotary distribution valve's common port, which is simultaneously
the hub and an external tubing attachment point) as well as reachable one
JUNCTION hop away at a neighboring port — both shapes are searched.

Hard-closed edges carry their queues forward unchanged. Junction traversal,
hub redistribution, and inventory resolution reject the same closed marker
independently of solved flow. Pockets below `MIN_POCKET_VOLUME` are discarded
at the end of each step.

`advance()` also reports departures: the volume that left the
inventory-connected end of each transport edge, which drives inventory
emission. `inject()` appends emitted pockets at the inflow end of each edge
and pads any underfilled edge with an air carrier pocket so transport edges
are always full.

## Inventory

Vessel inventory state is seeded from the inventory snapshots stored in the
compiled graph. During each step:

- Vessel pressure is refreshed from the hydraulic solve for *all* vessels
  (the solver is the authoritative pressure source).
- Arriving pockets increase the appropriate phase volume and species moles.
- Temperature is blended by thermal mass (`Σ n_i·Cp_i` over both phases,
  instantaneous equilibrium between phases). When no tracked species carry
  thermal mass, blending falls back to volume weighting with a warning.
- Departing volumes emit gas from `TOP` ports or liquid from `BOTTOM` ports,
  removing a proportional fraction of the phase's species. If the requested
  phase runs out, the deficit is filled with carrier (air for gas, computed
  from the ideal gas law) and a warning is logged.

### Flow sources and syringe pumps

`FlowSource` components compile to a single boundary node and emit pockets
directly into their outgoing transport edge each tick:

- Plain flow sources are infinite reservoirs: their declared concentration
  (`initial_species / content volume`) is constant and never depleted.
  `direction_upward` selects liquid (default) or gas emission.
- Syringe pumps are finite: the worker tracks the remaining liquid volume,
  decrements it on dispense, refills it on withdrawal (negative flow), and
  falls back to emitting air once the syringe runs dry (with warnings for
  run-dry and over-fill).

### Heat exchange

Vessels with `heat_exchange=True` get a Newton-cooling update each step:
`Q̇ = U·A·(T_wall − T_vessel)`, applied against the vessel's tracked-species
thermal mass. Multi-well components (e.g. vials) register one entry per
well. Vessels with zero thermal mass are skipped.

## Reactions

Reactions are attached through a `ReactionsMap`:

```python
{
    "reactor.Inventory": [reaction_1, reaction_2],
}
```

Any object with `step(state, dt) -> None` can be a reaction (structural
`Protocol`; mutates the inventory state in-place). Built-in reaction models
include `NullReaction`, `FirstOrderDecay`, and `StoichiometricReaction`.
Both kinetic models support an optional temperature change per mole
converted (positive = vessel heats up).

Inventory targets react after assimilation. FlowReactor and PhotoReactor
targets react every resident pocket after wall heat exchange and before
transport advances; pocket volume and pressure remain unchanged.

## Back-Pressure Regulators

The worker pre-resolves BPR edges at construction. A BPR is a one-way check
valve — it relieves pressure upstream to downstream only and must never carry
flow the other way — so every step, immediately after the hydraulic solve and
before anything else runs, `Worker._reseat_backward_bpr_edges` force-closes
(`R_MAX_HYDRAULIC`) any open BPR edge whose solved flow came out negative and
re-solves, repeating until no open BPR edge is backward. This is what
guarantees the check-valve invariant: the proportional throttle below treats
an open BPR as a plain (undirected) resistor, which on its own has no way to
stop a pressure shift elsewhere in the network from pulling flow backward
through it.

Once per step, after that guarantee holds, each BPR edge's resistance
override is updated for the next tick:

- While closed (`R_MAX_HYDRAULIC`), the upstream pressure is genuine: the
  edge stays closed below the setpoint and opens fully once the setpoint is
  reached.
- While open, a proportional model drives the upstream pressure toward the
  setpoint: `R = (setpoint − P_downstream) / |Q|`. If the downstream
  pressure already exceeds the setpoint, the override is cleared (fully
  open) and the network settles naturally — the reseat guarantee above
  applies regardless of how this heuristic chooses to throttle.

## Recorder

`Recorder` is the sole SQLite writer. It opens one WAL-mode connection at
construction and writes all dynamic tables atomically per record interval
(`record_interval` must be a multiple of `dt`). Transport edges are sliced
into fixed-length cells (`RECORDER_CELL_LENGTH_M`) for spatial snapshots of
pocket contents. The worker closes the recorder at the end of `run()`. GUI
readers must use their own read-only connections.

## Server / CLI

`chemunited-sim <project> [--port] [--db]` starts a FastAPI server
(uvicorn, default port 1472) that loads a project folder or `.chemunited`
ZIP, runs the worker in a background thread, and exposes endpoints to load
projects, start/stop simulations, send runtime component commands, and query
status. Each run writes its own SQLite database (and log file) under the
`--db` directory.
