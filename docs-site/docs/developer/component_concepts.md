# Component core concepts

Every pump, valve, sensor, and vessel you drag onto the [Draw](../drawing/drawing.md) canvas is, underneath the
icon, the same small set of building blocks arranged differently. This page explains that shared model —
independently of any single component — so that [Add new components](add_components.md) reads as "fill in these
blocks" rather than a list of unexplained rules.

<div class="info-block">
<strong>💡 Who this is for</strong><br>
You don't need this page to <em>use</em> ChemUnited — it's for anyone writing a new component in
<code>chemunited-core</code> (built-in or project-local), or who just wants to understand what a component
"really is" once it's compiled.
</div>

## Two objects, one component

Every component is described by a pair of Python objects, not one:

* **`ComponentMode`** — a Pydantic model. This is the *configuration*: the fields a user edits in the property
  panel, and what gets saved to the project's config files. Base fields every component has: `name` (its unique
  identifier — see the naming warning in [Drawing](../drawing/drawing.md#components--connections-properties)),
  `figure` (which catalog entry/icon it uses), `position`, `angle`, and `mirror`.
* **`ComponentData`** — a plain dataclass. This is the *compiled runtime structure*: the same base fields, plus
  the actual graph of ports, internal channels, and storage that the simulator and GUI both read.

A `ComponentData` is always built *from* a `ComponentMode`, never authored by hand — and stays in sync with it
every time the user edits a property:

<img src="../_static/diagrams/mode_data_lifecycle.svg" alt="ComponentMode and edited ComponentMode both feed ComponentData via from_mode/update; ComponentData fans out to internal_structure() and sync_internal_state()" style="max-width:100%;">

<div class="info-block">
<strong>💡 Rule of thumb</strong><br>
Put anything the user should configure or that must survive being saved on <code>*Mode</code>. Put the compiled
result — ports, edges, inventories, and any command-driven behavior — on <code>*Data</code>.
</div>

## Anatomy of a component's internal graph

`internal_structure()` is what every component implements to describe its own tiny internal graph. That graph is
built from four kinds of pieces:

### Ports — connection points

A `Port` is a physical connection point on the component — the little dot you draw a wire or a tube to/from on
the canvas. Each one has a `number` (unique within the component), a `category`, an `access` side (`TOP`/`BOTTOM`
— vessels use this to tell gas-side from liquid-side access), a `closure` (`OPEN`/`CAPPED`), and an optional
`boundary` (see below).

The `category` is one of the same four connection types you already choose between when wiring components
together on the canvas (see [Connections](../drawing/drawing.md#connections)) — the code names below match what
you'll see in `chemunited_core`; the canvas panel labels the first one "Flow" instead of "Hydraulic":

* <img src="../_static/flow_point.png" width="16" style="vertical-align:middle; margin-right:4px;"> **HYDRAULIC** — tubing that carries fluid.
* <img src="../_static/heat_point.png" width="16" style="vertical-align:middle; margin-right:4px;"> **HEAT** — thermal coupling used by the simulator only.
* <img src="../_static/electronic_point.png" width="16" style="vertical-align:middle; margin-right:4px;"> **ELECTRONIC** — a control-signal connection.
* <img src="../_static/movement_point.png" width="16" style="vertical-align:middle; margin-right:4px;"> **MOVEMENT** — sample transport (gantries, robotic arms).

A port can also be a hidden **hub** (`is_hub=True`, `show_in_graph=False`) — an internal staging node that never
appears on the canvas, used by pumps and distribution valves to model a shared internal manifold.

### Internal edges — channels inside the component

An `InternalEdge` is a directed path between two endpoints *inside* one component's own subgraph — most often
between two of its ports, but an endpoint can also be an inventory key (see below), letting an edge connect a
port straight into storage.

Every internal edge plays one of two roles:

<img src="../_static/diagrams/transport_junction_roles.svg" alt="TRANSPORT: Port 1 to Port 2 with resistance from geometry. JUNCTION: Port 1, 2, and 3 all connect losslessly into a hidden hub" style="max-width:100%;">

* **`TRANSPORT`** — a real physical channel (tubing, a reactor coil). Its hydraulic resistance is derived from
  `length` and `diameter` (Hagen–Poiseuille), unless overridden.
* **`JUNCTION`** — a near-lossless internal connection, used to join ports to a hidden hub or to an inventory
  node.

Any edge can be switched: `edge.close()` sets its resistance to the solver's effective-infinite constant
(`R_MAX_HYDRAULIC`); `edge.open()` clears the override so resistance goes back to being geometry-based. This is
the mechanism every valve uses — see [Switchable edge](#switchable-edge) below.

### Inventory nodes — lumped storage

An `InventoryNode` represents a well-mixed lump of storage — the inside of a flask, a reactor, a syringe barrel.
It holds two phases, `liq_content` and `gas_content`, each a `VolumeContentBase` (a volume, a phase, and the
moles of each chemical species it contains). A component can have zero inventory nodes (plain tubing), one (a
flask, keyed `"Inventory"` by convention), or several (a multi-well plate has one per well).

<img src="../_static/diagrams/inventory_node.svg" alt="InventoryNode holds liq_content and gas_content; liq_content holds initial_species, looked up by name in the COMPOUNDS registry" style="max-width:100%;">

The species *amounts* live on the component; the species' *physical properties* live once, project-wide, in the
`COMPOUNDS` registry — the same registry backing the **Compounds** page described in
[Setup Digital Twins](../simulation/digital_twins.md#compounds--initial-inventory).

### Boundary conditions — telling the solver what's fixed

A `Port.boundary` is a separate thing from `closure`: `closure` is the *physical* seal state (open vs. capped),
while `boundary` is a *hydraulic solver* constraint — what the port forces the simulated network to do.

<img src="../_static/diagrams/port_boundary.svg" alt="Port.boundary is None (ordinary port), PRESSURE with a value, or FLOW with a value" style="max-width:70%;">

A boundary isn't necessarily permanent — a gantry head, for example, switches its port's boundary between
atmospheric pressure (idle) and `None` (inserted into a vessel) as it moves, entirely inside
`sync_internal_state()`.

<div class="warning-block">
<strong>⚠️ Don't confuse the two</strong><br>
<code>PortClosure</code> (<code>OPEN</code>/<code>CAPPED</code>) is what the user physically did to the port.
<code>PortBoundaryCondition</code> is what the hydraulic solver assumes at that port. A capped port and a
pressure-boundary port can look identical on the canvas but mean very different things to the simulator.
</div>

## Two different things are both called "edge"

This is the single most common point of confusion, so it gets its own section: **`InternalEdge`** and
**`EdgeData`/`EdgeMode`** are not the same concept.

* `InternalEdge` lives *inside* one component's own `internal_edges` dict — private plumbing the component
  author defines (a valve's rotor channel, a reactor's coil).
* `EdgeData`/`EdgeMode` is the *process-level* connection you draw between two different components on the
  canvas — external tubing, with its own `length`, `diameter`, and `classification` (the same `HYDRAULIC` /
  `HEAT` / `ELECTRONIC` / `MOVEMENT` categories as ports).

Ports are the seam between the two graphs:

<img src="../_static/diagrams/edge_seam.svg" alt="Component A's Port 2 connects to Component B's Port 1 via a thick EdgeData connection, the tube drawn on the canvas, while each component's own ports are joined internally by a thin InternalEdge" style="max-width:100%;">

A component's own internal topology is invisible to its neighbors — all a neighboring component sees is the
port it's connected to.

## Common topology recipes

Most new components are one of a handful of recurring shapes. Picking the right one first makes everything else
(the `Mode` fields, the figure registry entry, the command methods) fall into place.

### Two-port inline transport

Tubing, loops, columns, flow reactors — anything where geometry alone determines resistance.

<img src="../_static/diagrams/topology/two_port_transport.svg" alt="Port 1 connects to Port 2 through a TRANSPORT edge, resistance derived from length and diameter" style="max-width:50%;">

<div class="component-examples">
<img src="../_static/components/Loop.svg" width="100" height="100"> 
<img src="../_static/components/FlowReactor.svg" width="100" height="100">
<div class="example-caption">Example components: Loop, Flow Reactor</div>
</div>

### Terminal fixed-flow

A component with one port that forces a flow rate onto the network — a flow source.

<img src="../_static/diagrams/topology/terminal_fixed_flow.svg" alt="The rest of the hydraulic network connects to Port 1, whose boundary condition forces a fixed flow rate" style="max-width:100%;">

<div class="component-examples">
<img src="../_static/components/SyringeBarrel.svg" width="100" height="100">
<div class="example-caption">Example component: Syringe Pump</div>
</div>

### Terminal fixed-pressure

A component with one port that forces a pressure onto the network — the strongest constraint in the system.

<img src="../_static/diagrams/topology/terminal_fixed_pressure.svg" alt="The rest of the hydraulic network connects to Port 1, whose boundary condition forces a fixed pressure setpoint" style="max-width:100%;">

<div class="component-examples">
<img src="../_static/components/PressureControl.svg" width="100" height="100">
<div class="example-caption">Example component: Pressure Control</div>
</div>

### Junction with hidden hub

A splitter or combiner: several visible ports meeting at one hidden internal hub through lossless `JUNCTION`
edges.

<img src="../_static/diagrams/topology/junction_hidden_hub.svg" alt="Port 1, Port 2, and Port 3 all connect into a hidden hub, Port 0" style="max-width:70%;">

<div class="component-examples">
<img src="../_static/components/Distributor.svg" width="100" height="100">
<div class="example-caption">Example component: Distributor</div>
</div>

### Vessel with inventory

Flasks, bottles, vials, wells — any storage object. Both ports connect to the same `InventoryNode` through
`JUNCTION` edges.

<img src="../_static/diagrams/topology/vessel_inventory.svg" alt="Port 1 (TOP) and Port 2 (BOTTOM) both connect through JUNCTION edges to the same InventoryNode" style="max-width:80%;">

<div class="component-examples">
<img src="../_static/components/GlassBottle.svg" width="100" height="100"> <img src="../_static/components/Vial.svg" width="100" height="100">
<div class="example-caption">Example components: Glass Bottle, Vial</div>
</div>

### Switchable edge

Valves, regulators, flow controllers — every possible internal edge already exists; only its open/closed state
changes.

<img src="../_static/diagrams/topology/switchable_edge.svg" alt="Side by side: open() leaves Port 1 to Port 2 with resistance from geometry; close() sets the same edge to R_MAX, effectively sealed" style="max-width:100%;">

<div class="component-examples">
<img src="../_static/components/SixPortDistributionValve.svg" width="100" height="100"> <img src="../_static/components/SolenoidValve.svg" width="100" height="100">
<div class="example-caption">Example components: Rotary Valve, Solenoid Valve</div>
</div>

<div class="info-block">
<strong>💡 Choosing the right shape</strong><br>
Ask what graph the simulator should see: one node that fixes flow → terminal fixed-flow. One node that fixes
pressure → terminal fixed-pressure. A physical channel → two ports and a TRANSPORT edge. A splitter/combiner →
visible ports plus a hidden JUNCTION hub. A storage object → ports plus an InventoryNode. A switch → every edge
exists, inactive ones are closed.
</div>

## Classification and the command interaction model

Every `ComponentData` carries a class-level `COMPONENT_TYPE`, either:

* **`ELECTRONIC`** — controlled by protocol commands (pumps, valves, controllers, analytical instruments).
* **`UTENSIL`** — passive physical equipment with no commands of its own (tubing, junctions, plain vessels).

This determines which runtime manager assembles it, and is exposed as the `is_electronic` property.

Electronically controlled components share one interaction contract, three methods:

* **`put(command, **kwargs)`** — pure validation/planning. Must not mutate anything.
* **`apply(command, **kwargs)`** — mutates the live component, calls `sync_internal_state()` if the change
  affects topology or boundaries, and returns a `PutResult`.
* **`get(command, **kwargs)`** — a read-only query (e.g. reading back a live temperature).

A `PutResult` can also carry `scheduled: list[ScheduledCommand]` — follow-up commands to fire automatically after
a delay, without the caller having to track time itself. A syringe pump's `infuse` command uses exactly this to
schedule its own `stop`:

<img src="../_static/diagrams/infuse_stop_sequence.svg" alt="Sequence diagram: Caller puts and applies infuse on Data, which mutates fields, syncs internal state, and returns a PutResult scheduling a follow-up stop; after a delay the scheduler applies stop, which syncs internal state again" style="max-width:100%;">

<div class="component-examples">
<img src="../_static/components/HPLCPump.svg" width="100" height="100"> <img src="../_static/components/SolenoidValve.svg" width="100" height="100">
<div class="example-caption">Example components: HPLC Pump, Solenoid Valve</div>
</div>

A simpler, synchronous example: a solenoid valve's `apply("open")` just flips a boolean and calls
`sync_internal_state()`, which opens or closes its internal edges to match — no scheduling involved.

## Declaring the command vocabulary

`apply()`/`put()` is *where* a command executes. What commands exist in the first place, and their typed
parameters, is declared separately in `chemunited_core.protocols`: a `CommandSignature` per command, grouped into
a `ComponentProtocol` for the component's `figure` type. This is deliberately declarative — no networking code
belongs there, only names and parameters.

You've already seen the user-facing side of this without necessarily connecting it to the component model: the
[Command module](../protocols/command.md) you drag from the Command List onto a workflow canvas is built from
exactly this declared vocabulary, and generates code that calls straight into `put()`:

```python
def command_1(self, ctx: NodeExecutionContext) -> bool:
    self.platform["pt100"].put(
        "power-on",
        description="Turn on temperature controlling",
    )
    return True
```

## The `figure` name is the join key

A component's `figure` string (the same value set on both `ComponentMode.figure` and `ComponentData.figure`) is
what ties three otherwise-independent registries together:

<img src="../_static/diagrams/figure_join_key.svg" alt="figure = SolenoidValve ties together the figure_registry ComponentDefinition, the SolenoidValve.svg icon, and the protocol registry's ComponentProtocol" style="max-width:100%;">

This is exactly what lets a project-local `components/` folder register a fully working custom component —
`register_component()` plus `register_figure()`/an adjacent `.svg`, plus `register_protocol()` if it's
electronic — without touching `chemunited-core` at all, as shown in
[Add new components](add_components.md#from-your-own-project-no-chemunited-core-changes-needed).

## Worked example: mixing hydraulic and electronic ports

A component isn't limited to one connection type. A UV/Vis flow-cell detector, for example, is hydraulically a
plain two-port channel — but it also needs an electronic port to report its reading, and is classified
`ELECTRONIC` so it can be commanded (e.g. to change its monitored wavelength):

<img src="../_static/diagrams/uv_flow_cell_example.svg" alt="UV Flow Cell, COMPONENT_TYPE ELECTRONIC: Port 1 (HYDRAULIC) connects to Port 2 (HYDRAULIC) via a TRANSPORT edge; Port 3 (ELECTRONIC) stands alone reporting wavelength/signal" style="max-width:100%;">

Its `port_pairs` are `[(1, 2), (3,)]` — ports 1 and 2 form the valid hydraulic pass-through pair, and port 3 is
its own standalone group with no hydraulic partner. `internal_edges` only contains the `(1, 2)` transport edge;
port 3 needs none, since nothing flows through it. This is the general pattern for any electronically-controlled
component that also sits inline in the fluid path — the two concerns (hydraulics and commands) are declared
independently and simply coexist on the same component.

## Where to go next

* Ready to write one? → [Add new components](add_components.md) walks through the practical steps and file
  layout.
* Want to see the whole catalog these shapes produce? → [Components available](../reference/components.md).
* Want to change what happens to a vessel's *chemical contents* over time, rather than its structure? →
  [Customize protocols](add_features.md) covers reaction models, the layer above everything on this page.
