# Workflows Module

The `chemunited.protocols.workflows` package is the visual authoring layer for protocol workflows in the Qt setup window.

Its job is to let the user design a process as a directed graph, keep that graph editable in memory, render it on the canvas, and save or reload it through generated Python `build_workflow()` methods.

If you want one sentence for the whole module, it is this:

`ProcessWorkflow` is the source of truth for one process, `WorkflowController` is the only writer, `WorkflowGraph` is the interactive canvas, and `WorkflowsWidget` manages one canvas per process.

The companion file `workflows.drawio` shows the same architecture visually.

## Scope

This module does:

- authoring and editing of protocol workflows
- block and connection validation
- Qt scene rendering for blocks, ports, and edges
- process switching between multiple workflows
- save and load adaptation between the editor model and generated process Python

This module does not do:

- workflow compilation
- workflow execution
- scheduling runtime iterations
- hardware interaction

Those runtime concerns live in the separate `chemunited_workflow` package. The workflows editor only produces and restores the authored graph that runtime code consumes later.

## Core Mental Model

There are three layers to keep in mind:

1. Integration layer
   `SetupWindow`, `ProtocolsWidget`, `CommandList`, and `OrchestratorProtocols` decide which process exists and which one is active.

2. Editor layer
   `WorkflowsWidget`, `WorkflowGraph`, and the graphics items provide the visible editor and all user interactions.

3. Model and persistence layer
   `ProcessWorkflow`, `BlockData`, `ConnectionData`, `storage.py`, and `project_file.py` hold the workflow state and translate it to and from saved Python process classes.

One process is represented by three linked objects:

- one `ProcessWorkflow`
- one `WorkflowController`
- one `WorkflowGraph`

`WorkflowsWidget` stores those per process and shows the active graph through a `QStackedWidget`.

## Main Objects

| Object | File | Responsibility |
| --- | --- | --- |
| `ProcessWorkflow` | `process_workflow.py` | In-memory graph model for one process. Wraps a `networkx.DiGraph`. |
| `BlockData` | `process_workflow.py` | Node data model used by the editor. Extends `WorkflowNodeSpec` with Qt/editor metadata. |
| `ConnectionData` | `process_workflow.py` | Edge data model used by the editor. Stores routing and branch or loop semantics. |
| `WorkflowController` | `controller.py` | The write gate. Validates and applies mutations to `ProcessWorkflow`, then emits Qt signals. |
| `WorkflowGraph` | `workflow_frames.py` | Interactive canvas. Converts model state into scene items and forwards user gestures to the controller. |
| `WorkflowsWidget` | `workflow_widget.py` | Process-level container. Owns one controller and one graph per process and switches between them. |
| `workflow_rules.py` | `workflow_rules.py` | Pure workflow rules: terminal nodes, naming, connection validation, and edge metadata derivation. |
| `WorkflowNode` | `elements/work_node.py` | Visual node item with shape, icon, progress bar, and ports. |
| `WorkflowConnection` | `elements/work_connection.py` | Visual edge item with routing, labels, color semantics, and inflection handles. |
| `WorkflowAccessPoints` | `elements/access_point.py` | Visual port groups used to start or end connections. |

## Data Contracts

### `BlockData`

`BlockData` is the editor-side node model. It inherits the runtime-facing fields from `WorkflowNodeSpec`:

- `node_id`
- `method`
- `label`
- `description`
- `position`

It adds editor-only fields:

- `process`
- `file`
- `block_tag`
- `ports_numbers`
- `file_path`
- `protected`

Why this matters:

- the runtime world cares about `WorkflowNodeSpec`
- the editor world also needs visual type information, port counts, file references, and protection flags

`BlockData.to_script()` bridges the two by rendering a Python `graph.add_node(...)` call that includes both:

- the runtime-friendly `WorkflowNodeSpec(...)`
- editor metadata such as `block_tag` and `ports_numbers`

### `ConnectionData`

`ConnectionData` is the editor-side edge model. It stores both branch or loop meaning and edge geometry:

- `start_role`
- `condition`
- `loopback`
- `trigger_on`
- `label`
- `inflection_points`
- `max_iterations`

Meaning of the important fields:

- `start_role` tells the view which side of the source block the edge starts from
- `condition` marks true or false branches for conditional flow
- `loopback` marks loop edges
- `trigger_on` distinguishes which runtime result triggers a loopback
- `inflection_points` stores user-adjusted bend guides for orthogonal routing

### `ProcessWorkflow`

`ProcessWorkflow` owns the real editor state for one process.

Important responsibilities:

- wraps a `networkx.DiGraph`
- stores `BlockData` on nodes and `ConnectionData` on edges
- auto-creates protected terminal blocks through `ensure_terminal_blocks()`
- exposes mutation helpers such as `add_block`, `move_block`, `add_connection`, and `update_connection_geometry`
- exports a plain `networkx` graph through `as_networkx()`

Protected terminal blocks:

- `start`
- `end`

They always exist, are re-created after `clear()`, and cannot be deleted through normal editor actions.

## Module Architecture

### 1. Integration Layer

The workflows editor is mounted into the setup UI from `src/chemunited/setup.py`.

Relevant host objects:

- `SetupWindow`
  creates `protocolFrame`, `workflows_protocol`, `protocols_widget`, and `command_list`
- `OrchestratorProtocols`
  owns the authoritative `self.protocols: dict[str, ProcessWorkflow]`
- `ProtocolsWidget`
  sends add, rename, remove, duplicate, and select actions for processes
- `CommandList`
  provides drag-and-drop command entries into the workflow canvas

The important ownership rule is:

`OrchestratorProtocols` is the single writer for the process dictionary, and each dictionary value is a `ProcessWorkflow`.

### 2. Editor Container Layer

`WorkflowsWidget` is the process switcher for the workflow editor.

It owns:

- `workflows: dict[str, WorkflowGraph]`
- `controllers: dict[str, WorkflowController]`
- `stacked_graphs: QStackedWidget`

When a process is added:

1. `OrchestratorProtocols.add_process()` creates a new `ProcessWorkflow`
2. it passes that workflow into `WorkflowsWidget.add_process()`
3. `WorkflowsWidget` creates a `WorkflowController(workflow=graph)`
4. `WorkflowsWidget` creates a `WorkflowGraph(controller=controller)`
5. the graph is inserted into the stacked widget and becomes the active view

This keeps each process isolated while sharing the same outer UI.

### 3. Canvas Layer

`WorkflowGraph` is the interactive `QGraphicsView`-based editor for one process.

It is responsible for:

- drawing the grid background
- zooming
- building the scene from model data
- node and connection context menus
- delete-key handling
- drag and drop from `CommandList`
- connection creation through access-point clicks
- forwarding geometry changes back into the model

`WorkflowGraph.build_from_model()` is the main render entry point:

1. clear the scene
2. iterate `controller.iter_blocks()`
3. create `WorkflowNode` items
4. iterate `controller.iter_connections()`
5. create `WorkflowConnection` items
6. sync input port counts based on non-loopback incoming edges

### 4. Mutation Layer

`WorkflowController` is the only object that should mutate a `ProcessWorkflow`.

That is a core architectural rule of this package.

The controller:

- generates block names
- validates connection requests
- derives edge metadata
- updates the model
- emits signals so the view can redraw incrementally

Main signals:

- `model_reset`
- `block_added`, `block_updated`, `block_removed`
- `connection_added`, `connection_updated`, `connection_removed`
- `command_block_added`

Important pattern:

- the view does not edit the graph directly
- the view asks the controller
- the controller changes the model
- the controller emits signals
- the view reacts to those signals

This keeps rendering and state changes separated.

### 5. Rules Layer

`workflow_rules.py` is the domain-policy module.

It keeps rule logic out of the view and mostly out of the model.

It currently owns:

- terminal block definitions for `start` and `end`
- automatic block naming for `script`, `loop`, `conditional`, and `command`
- connection validation
- edge metadata derivation from source block type and source port
- helper logic for incoming input port counts
- helper logic for re-deriving a render-side `start_role` when loading a saved graph

This file is the best place to change workflow semantics without touching Qt painting code.

### 6. Scene Elements Layer

The actual scene is drawn with three main graphics item types.

#### `WorkflowNode`

`WorkflowNode` renders a block as a shaped item:

- `START` and `END` are circles
- `SCRIPT` is a rounded rectangle
- `LOOP` is a hexagon-like repeat shape
- `IF` is a diamond
- `COMMAND` uses the regular non-terminal card style

It also owns:

- title and subtitle text
- SVG icon
- optional progress bar
- left, right, top, and bottom access-point groups depending on block type

Port layout rules:

- `START` has no input ports
- `END` has no output ports
- `IF` and `LOOP` add top and bottom special ports
- input port count can grow based on incoming non-loopback edges

#### `WorkflowAccessPoints`

`WorkflowAccessPoints` is the visual group of clickable ports.

Important behavior:

- left-side groups are valid connection targets
- right, top, and bottom groups are valid connection starts
- selection state is used when the user is building a connection

#### `WorkflowConnection`

`WorkflowConnection` renders an orthogonal edge with rounded corners and an arrow head.

It also handles:

- semantic coloring
- label text
- dashed styling for loopbacks
- one or two user-adjustable inflection points
- draggable inflection handles when selected

Routing behavior:

- if the edge has stored `inflection_points`, they guide the orthogonal route
- otherwise the route is auto-generated from source and destination anchors

## How Editing Works

This is the typical flow for user actions.

### Add a block

1. User right-clicks on empty canvas
2. `WorkflowGraph._build_add_menu()` offers block types
3. `WorkflowGraph.add_block()` calls `WorkflowController.add_block()`
4. the controller asks `workflow_rules.generate_block_name()`
5. the controller writes the new `BlockData` into `ProcessWorkflow`
6. the controller emits `block_added`
7. `WorkflowGraph._on_block_added()` creates the corresponding `WorkflowNode`

### Connect two blocks

1. User clicks a source access-point
2. `WorkflowGraph` stores it as `_selected_port`
3. User clicks a destination input access-point
4. `WorkflowGraph` calls `WorkflowController.connect_nodes(...)`
5. the controller validates with `validate_connection_request(...)`
6. the controller derives edge semantics with `derive_connection_attributes(...)`
7. the controller stores a `ConnectionData`
8. the controller emits `connection_added`
9. `WorkflowGraph` creates the `WorkflowConnection`

### Move a block

1. User drags a `WorkflowNode`
2. `WorkflowNode.itemChange(...)` calls the `on_position_changed` callback
3. `WorkflowGraph._on_node_moved()` updates edge rendering and calls `controller.move_block(...)`
4. `ProcessWorkflow` updates the saved `position`

### Bend an edge

1. User selects a connection
2. `WorkflowConnection` shows inflection handles
3. dragging a handle updates `inflection_points`
4. `WorkflowGraph._on_connection_geometry_changed()` forwards geometry to the controller
5. `ProcessWorkflow.update_connection_geometry()` stores the new points

### Delete an item

1. User presses Delete or uses a context menu
2. `WorkflowGraph` resolves the selected scene item back to node or edge names
3. removal goes through the controller
4. controller emits removal signals
5. graph removes scene items and resyncs input port counts

## Workflow Semantics

### Supported block types

- `START`
- `END`
- `SCRIPT`
- `LOOP`
- `IF`
- `COMMAND`

### Conditional edges

For conditional blocks:

- false branches render from the top port
- true branches render from the bottom port

This meaning is derived from the source block type and source port, not from arbitrary edge styling.

### Loop edges

Loop-specific edges are marked with `loopback=True`.

The current editor rules enforce:

- a loop block can have only one outgoing loopback
- input port counts ignore loopback edges, because loopbacks do not represent independent external predecessors

### Terminal blocks

`start` and `end` are always present and protected.

This simplifies both editing and persistence because every workflow has stable entry and exit anchors.

## Save and Load Architecture

The most important design choice in this editor is that workflows are persisted as Python process code, not as a dedicated workflow JSON file.

### Save path

When a project is saved:

1. `OrchestratorProjectFile._save_protocols()` iterates `self.protocols`
2. `ProjectSession.sync_process(name, workflow)` is called
3. `storage.sync_process(...)` updates or creates the process Python file
4. `storage._render_workflow_definition(workflow)` renders each node and edge
5. `BlockData.to_script()` writes `graph.add_node(...)`
6. `ConnectionData.to_script()` writes `graph.add_edge(...)`
7. the saved process class now contains a `build_workflow()` method that reproduces the authored graph

What is persisted for blocks:

- runtime `WorkflowNodeSpec` data
- `block_tag`
- `ports_numbers`
- `position`
- optional labels and descriptions

What is persisted for edges:

- normal edge conditions and labels through `WorkflowEdgeSpec`
- edge routing geometry through `inflection_points`
- loopback metadata through explicit edge kwargs

### Load path

When a project is opened:

1. `ProjectSession.load_process_classes()` imports the saved process classes
2. `OrchestratorProjectFile._restore_protocols()` iterates those classes
3. `_workflow_from_process_class(name, cls)` instantiates the class and calls `build_workflow()`
4. nodes and edges from the resulting `networkx` graph are converted back into a fresh `ProcessWorkflow`
5. `WorkflowsWidget.add_process(...)` rebuilds the editor view for that workflow

Important restore details:

- `block_tag` is restored from saved node attrs when present
- older files can still infer block type heuristically
- edge source ports are re-derived through `resolve_render_start_role(...)`

## Where Runtime Starts

The output of this editor is a Python `build_workflow()` method that returns an authored `nx.DiGraph`.

That graph is later consumed by the runtime package:

- `chemunited_workflow.models`
- `chemunited_workflow.compiler`
- `chemunited_workflow.executor`
- `chemunited_workflow.process`

So the editor is upstream of compilation and execution, but it is not the executor itself.

## Current Caveats

These are important for understanding the current architecture exactly as it exists today.

### Command block payload is not part of `BlockData`

Dropping an item from `CommandList` creates a `COMMAND` block and emits `command_block_added(command, component)`.

At the moment, the actual `ProcessWorkflow` model stores the resulting node as a normal block with `block_tag=COMMAND`, but it does not store the `command` and `component` payload itself inside `BlockData`.

That signal is therefore an integration hook, not a complete persistence story by itself.

## File-by-File Map

- `__init__.py`
  public exports for the package
- `process_workflow.py`
  data model and graph wrapper
- `controller.py`
  the mutation gateway and Qt signal source
- `workflow_widget.py`
  process-level container and stacked switcher
- `workflow_frames.py`
  interactive canvas and scene coordination
- `workflow_rules.py`
  pure workflow semantics and helper rules
- `elements/work_node.py`
  node painting and ports
- `elements/work_connection.py`
  edge painting, routing, labels, and inflection handles
- `elements/access_point.py`
  interactive ports
- `design.py`
  state-to-color helpers used by workflow visuals
- `exceptions.py`
  editor-specific exceptions

## How To Extend The Module Safely

### Add a new block type

You will usually need to touch all of these places:

1. `ProtocolBlock`
   add the enum value
2. `workflow_rules.py`
   decide naming, validation, and render-role semantics
3. `elements/work_node.py`
   define shape, icon, colors, and port layout
4. `workflow_frames.py`
   expose the block in the add menu and display labels
5. `process_workflow.py`
   make sure block persistence includes the needed metadata
6. `project_file.py`
   teach restore logic how to recognize the new type

### Add new edge metadata

You will usually need to update:

1. `ConnectionData`
2. `ConnectionData.to_attrs()`
3. `ConnectionData.to_script()`
4. `WorkflowConnection.sync_from_model()`
5. `WorkflowController.connect_nodes()` or update methods
6. `project_file.py` restore logic

### Change workflow semantics

Prefer changing `workflow_rules.py` first.

That keeps semantics centralized and avoids scattering rules across:

- Qt menus
- scene rendering
- persistence code
- model storage

## Summary

If you remember only a few things, remember these:

- `ProcessWorkflow` is the model for one process
- `WorkflowController` is the only writer to that model
- `WorkflowGraph` is the interactive canvas for one model
- `WorkflowsWidget` manages one graph per process
- `workflow_rules.py` owns the semantics
- saving and loading happen through generated Python `build_workflow()` code
- runtime execution is outside this module
