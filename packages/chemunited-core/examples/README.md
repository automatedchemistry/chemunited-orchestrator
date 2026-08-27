# Examples

This folder contains small runnable examples for `chemunited-core`.

## Valve Flow Graph

Run the example from the repository root:

```bash
python examples/build_valve_graph.py
```

The script builds a small flow setup with:

- a flow source
- a pressure control node
- a feed vessel
- a junction
- a selector valve
- a plug-flow reactor
- a back-pressure regulator
- a product vessel
- a waste vessel

The generated graph is port-based:

- each equipment port is rendered as a node
- only hydraulic `FLOW` ports are shown
- vessel inventories are rendered as internal nodes
- component internal edges are shown separately from process connections
- active valve routes are highlighted while inactive routes stay dashed

If `pyvis` is installed in your environment, the script also writes an HTML graph to:

```text
examples/output/valve_flow_graph.html
```

Install `pyvis` only if you want the visualization step:

```bash
pip install pyvis
```
