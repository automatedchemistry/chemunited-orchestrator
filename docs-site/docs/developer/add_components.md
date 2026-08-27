# Add new components

Components are the drawable building blocks (pumps, valves, sensors, vessels...) available in the
[Draw](../drawing/drawing.md) canvas. See [Components available](../reference/components.md) for the full
current library. This page is for adding a new one that isn't in that list.

<div class="info-block">
<strong>💡 New to the component model?</strong><br>
This page is a practical how-to. For the theory behind ports, internal edges, inventories, boundary conditions,
and the electronic command interface referenced throughout it, read
<a href="component_concepts.md">Component core concepts</a> first.
</div>

## From your own project (no chemunited-core changes needed)

For a component that's specific to your own setup, you don't need to touch `chemunited-core` at all — no
editable install, no fork, no reinstall. Add a `customizations/components/` folder next to your project's existing
`draw/` and `protocols/` folders:

```text
your_project/
  customizations/
    components/
      __init__.py       # from . import my_valve
      my_valve.py        # data/mode classes + registration — no GUI dependencies
      MyValve.svg          # figure, same folder, named after it
      graph.py              # optional: custom rendering (multiple layers, animation, state-driven appearance)
  draw/setup.py
  protocols/__init__.py
```

`customizations/components/__init__.py` is loaded automatically the moment the project is opened — in the
orchestrator GUI and in chemunited-sim alike — and your component is immediately usable in `draw/setup.py` and shows
up in the canvas's Add tree under its own **Custom** category. See `chemunited-core`'s `Instruction.md` — the
"Building a Component in Your Own Project" section — for the full walkthrough, including how to declare commands for an electronically
controllable component and how to write a custom `graph.py` for multi-layer or animated rendering.

Use this path unless you specifically want the component to ship as part of the shared catalog for every
chemunited project — that's what the rest of this page covers.

## Anatomy of a Component

Most components live in `chemunited-core`, not in the orchestrator itself. A component definition has three parts:

* A **data class** describing its type and behavior (e.g. `ComponentType.ELECTRONIC`, `ComponentType.VALVE`).
* A **mode class** describing its user-editable parameters (the fields shown when you configure it on the canvas).
* An entry in the shared `COMPONENTS` registry that ties the two together, along with its **category** (which
  section of the Add tree it appears in, matching the categories in
  [Components available](../reference/components.md)) and its **port positions**.

For most new components — anything that behaves like a simple pass-through device — this registry entry is
**all** you need to write. The orchestrator auto-generates the canvas figure, tree entry, and property editor from
it; no changes to the orchestrator itself are required.

See [Component core concepts](component_concepts.md#common-topology-recipes) for the small set of internal
shapes (inline transport, terminal source, junction, vessel, switchable edge) most new data classes are built
from.

## Steps to Add a Component

<div class="info-block">
<strong>💡 Note</strong><br>
For anything beyond a simple pass-through device, <code>chemunited-core</code>'s own <code>Instruction.md</code>
("How to Build a New Component") covers this in much more depth than the summary below — lifecycle diagram, base
classes to subclass from, and the full <code>ComponentMode</code> field-metadata conventions.
</div>

1. Define the component's data/mode classes in `chemunited-core` (or reuse an existing base if your component is
   a variant of one, e.g. another valve port/position combination).
2. Add an entry for it to the shared `COMPONENTS` registry, giving it a name, category, and port positions.
3. Provide its canvas icon as an SVG (see below) — this is picked up automatically once named correctly.
4. (Optional) If the component needs custom rendering beyond the default auto-generated shape, add an explicit
   subclass in the orchestrator's component glossary instead of relying on auto-generation.
5. (Optional) For simulation support, give the component a resistance/behavior model in `chemunited-sim` so it can
   be included in [digital twin](../simulation/digital_twins.md) runs — see the reaction-model contract in
   [Customize protocols](add_features.md) for the equivalent idea on the reaction side.

<div class="info-block">
<strong>💡 Note</strong><br>
New components without simulation support still work perfectly for real-hardware runs — only <strong>Run
Simulation</strong> coverage is affected.
</div>

## Icons

Two icons are involved: the full canvas figure (the shape drawn on the platform) and the small icon shown in the
Add tree panel — the same icon set documented in
[Components available](../reference/components.md). Name new icon files after the component, following the
existing convention (`ComponentName.svg`, with a `LIGHT`/`DARK` theme-pair variant where applicable).

## Simplest example

The **Source** and **Sink** components (see the Generic category in
[Components available](../reference/components.md)) are the simplest possible components — a registry entry with no custom orchestrator code at all — and are a good starting
template to copy when adding a new simple component.
