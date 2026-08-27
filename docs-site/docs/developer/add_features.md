# Customize protocols

[Add new components](add_components.md) covers adding new *hardware* to the component library. This page covers
adding new *behavior* — logic layered on top of an existing platform, such as how a reaction is modeled in
simulation, or how the protocol logic itself is structured.

## <img src="../_static/icons/module.svg" width="16" style="vertical-align:middle; margin-right:4px;"> Custom Reaction Models

When simulating a process (see [Setup Digital Twins](../simulation/digital_twins.md)), `chemunited-sim` needs a
model for how the chemical content of a vessel changes over time. Three models are built in:

* **NullReaction** — no reaction; inventory only changes through mixing/transport.
* **FirstOrderDecay** — a single species decays at a fixed rate.
* **StoichiometricReaction** — a defined stoichiometric reaction converts reactants to products at a given rate.

All three follow the same minimal contract — a `step(state, dt)` method that advances the chemical state by one
time step. Advanced users can write their own reaction model by implementing this same contract and attaching it
to the relevant vessel/component, without touching the hydraulic or transport logic.

## Custom Modules & Parameters

Workflow modules and parameters are themselves a kind of "custom feature" — see
[Process workflow](../protocols/module_workflows.md) for building Script/Loop/Conditional modules, and
[Parameters](../protocols/parameters.md) for the supported parameter types. Those pages cover the everyday,
GUI-first way of extending a protocol's behavior; this page is for the lower-level extension points underneath.

## Next steps

See [Working with Backend](backend.md) for the project file format and MCP/API surfaces these features read from
and write to.
