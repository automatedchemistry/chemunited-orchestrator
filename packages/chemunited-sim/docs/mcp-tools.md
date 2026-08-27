# MCP Tools

When running with `--with-mcp` (MCP streamable-HTTP endpoint embedded in the FastAPI server at `/mcp`), the following tools are exposed to a connected LLM agent. No authentication — local-only, matching the REST API's `127.0.0.1` default.

## Typical loop

1. `load_project` a project directory or `.chemunited` ZIP.
2. `start_simulation` — this returns immediately; the run continues on a background thread.
3. Poll `get_status` until `sim_status` is `idle`.
4. `list_result_series` to discover the node/edge identifiers recorded for this run.
5. `get_latest_state` for a cross-sectional check, or `get_node_profile`/`get_edge_profile` for how a value evolved over the whole run, to judge whether the process is feasible.

## Project & status

| Tool | Description |
|------|-------------|
| `load_project` | Load or replace the active project from a directory or `.chemunited` ZIP. Rejected while a simulation is running. |
| `get_project` | Return the currently loaded project's path, components, and processes. |
| `get_status` | Return `sim_status` (`no_project`/`idle`/`running`), `current_t`, and the active `SimConfig`. |

## Run control

| Tool | Description |
|------|-------------|
| `start_simulation` | Start a run (`execution_id`, `dt`, `t_end`, `real_time`, `historical_file`). Returns immediately. |
| `stop_simulation` | Abort the running simulation and return to idle. The database is kept as-is. |
| `send_component_command` | Enqueue a component command during a real-time (mode 2) run, mirroring a command executed on real hardware. |

## Results & analysis

| Tool | Description |
|------|-------------|
| `list_result_series` | List the node/edge identifiers recorded in the current run's database. |
| `get_latest_state` | Cross-sectional snapshot: every node's pressure, every edge's flow, and each inventory's temperature/content, at the most recently recorded time. |
| `get_node_profile` | Full-run time series for one node: pressure, temperature, and per-phase species content (moles). Accepts `tail` to limit to the last N points. |
| `get_edge_profile` | Full-run time series for one edge: flow rate and average cell temperature where recorded. Accepts `tail` to limit to the last N points. |

Units are standardized across all three result tools — bar, mL/min, K — matching what the HTML dashboard shows a human, not the raw Pa/m³/s used internally. Every field in the response is unit-suffixed (`pressure_bar`, `flow_mlmin`, `temperature_k`).

A vessel's inventory node is recorded under `"<component_name>.Inventory"` (e.g. `reactor.Inventory`), distinct from the component's plain hydraulic port nodes (e.g. `reactor.1`) — use `list_result_series` rather than guessing.

## Human-facing outputs

| Tool | Description |
|------|-------------|
| `get_simulation_db` | Absolute path of the active or last simulation database. |
| `get_simulation_visualization` | Render and save the interactive pyvis graph + HTML dashboard for the latest recorded snapshot; returns their absolute paths. Intended for pointing a human user at a visual report — prefer the results tools above for the agent's own analysis. |
