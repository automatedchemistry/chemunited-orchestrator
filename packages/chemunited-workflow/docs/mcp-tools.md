# MCP Tools

When running with `--with-mcp` (MCP streamable-HTTP endpoint embedded in the FastAPI server at `/mcp`), the following tools are exposed to the connected LLM agent:

## Project

| Tool | Description |
|------|-------------|
| `load_project` | Load or switch the active project by directory path. Rejected if a run is active. |
| `get_project` | Return the currently loaded project path, or null if none is loaded. |

## Processes

| Tool | Description |
|------|-------------|
| `list_processes` | Discover available process names and schemas. |
| `get_process_schema` | Full parameter schema for a named process. |
| `read_process` | Source code of a process definition file. |

## Protocols

| Tool | Description |
|------|-------------|
| `list_protocols` | List protocol files in `protocols_historic/`. |
| `get_protocol` | Read a protocol file's full JSON content. |
| `create_protocol` | Validate and save a new versioned protocol file. |
| `delete_protocol` | Permanently delete a protocol file. |

## Run control

| Tool | Description |
|------|-------------|
| `start_run` | Execute a protocol file; returns a `run_id`, or an error if a run is already active. Pass `record_monitoring=True` to also persist monitored readings to `log/monitoring/{run_id}/` — errors instead of starting the run if no monitoring variables are registered. |
| `get_active_run` | Return the active run ID without consuming queued execution events. |
| `get_run_status` | Poll run state and events (clears the event queue on each call). |
| `get_run_report` | Full per-step execution report for the current or last completed run. |
| `cancel_run` | Cancel the active run (cooperative — stops at the next step checkpoint). Works whether the run is `running` or `paused`. |
| `pause_run` | Pause the active run (cooperative — holds at the next checkpoint, which may be mid-node between device calls). Hardware is left as-is. Only valid while `running`. |
| `resume_run` | Resume a paused run from exactly where it held. Only valid while `paused`. |
| `drain_run_pool` | Return all pending device commands from `log/pool/` and delete their files. |

## Components

| Tool | Description |
|------|-------------|
| `get_components` | Return the device connectivity map (`connectivity/associations.json`). |
| `ping_components` | Check reachability of all device URLs, including live device status via `/is-reachable` when supported. |
| `ping_component` | Check reachability of a single named device, including live device status via `/is-reachable` when supported. |

## Monitoring

| Tool | Description |
|------|-------------|
| `discover_component_commands` | List GET commands a component exposes via its live OpenAPI schema. |
| `get_monitoring_config` | Return the current monitoring registration (sample time, timeout, variables). |
| `set_monitoring_config` | Register which variables to monitor; persisted to `connectivity/monitoring.json`. |
| `get_monitoring_state` | Return `{manual_on, run_active, recording, run_id, effective_on}` — there is no session id. |
| `start_monitoring` | Turn monitoring on manually using the current config. Fails while a protocol run has monitoring forced on. |
| `stop_monitoring` | Turn monitoring off manually. Fails while a protocol run has monitoring forced on. |
| `get_monitoring_latest` | Return the latest reading per registered variable. |
| `get_monitoring_history` | Return the bounded in-memory reading history for one variable — the live visualization buffer. |
| `get_monitoring_profile` | Read back the full recorded profile for one variable from a past run started with `record_monitoring=True`. |

## Logs

| Tool | Description |
|------|-------------|
| `list_logs` | List log files, most recent first. |
| `read_log` | Read a log file's text content. |
| `search_logs` | Search log files for a query string (case-insensitive). |

---

The schemas returned by `list_processes` and `get_process_schema` contain
JSON-compatible defaults. Custom validated defaults are serialized using their
configured Pydantic field serializers.

See [Deployment Modes](deployment.md) for how to start the server with the MCP endpoint.

---

[← Back to README](../README.md)
