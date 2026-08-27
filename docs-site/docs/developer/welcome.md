# Developer Welcome

The rest of the documentation covers using ChemUnited entirely through the GUI. This section is for users who
want to go further: writing a new hardware component, customizing orchestrator behavior, scripting a project
headlessly, or automating it through an MCP-connected agent.

<div class="info-block">
<strong>💡 Note</strong><br>
This section assumes basic Python familiarity. If you only use the desktop app, you do not need to read past this
page.
</div>

## The Three Layers of ChemUnited

ChemUnited is split across a few independent packages rather than one monolith. In everyday use you mostly only
see the first one, but it helps to know all three exist:

* **The orchestrator** — the desktop app you draw platforms and build protocols in (everything covered in
  [Drawing](../drawing/drawing.md), [Building Protocols](../protocols/build_protocols.md), and
  [Connect Devices](../connectivity/connectivity.md)).
* **The work-server** (`chemunited-workflow`) — the engine that actually executes a protocol against real
  hardware once you click **Run Monitoring**. It runs as its own process and exposes a browser dashboard and API —
  see [The Dashboard](../dashboard/overview.md).
* **The simulation engine** (`chemunited-sim`) — the physics engine behind **Run Simulation** and digital twins —
  see [Setup Digital Twins](../simulation/digital_twins.md).

The full picture — how these fit together, plus the project file format they all share — is in
[Software design](software_design.md).

## Where to go next

* Want to understand the architecture? → [Software design](software_design.md)
* Want to understand what a Component actually is under the hood — ports, edges, inventories, commands? →
  [Component core concepts](component_concepts.md)
* Want to add a new pump/valve/sensor to the component library? → [Add new components](add_components.md)
* Want to script custom data-saving, reaction models, or orchestrator behavior? → [Customize protocols](add_features.md)
* Want to customize the browser dashboard's look or pages? → [Customize dashboard](customize_dashboard.md)
* Want to automate a project through MCP, or understand the on-disk project format? → [Working with Backend](backend.md)
