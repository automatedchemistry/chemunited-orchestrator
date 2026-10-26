# API Reference

When running in FastAPI mode the following endpoints are available.

All endpoints except `GET /project/` return HTTP `503` if no project has been loaded yet.

## Project management

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/project/` | Return the currently loaded project directory, or `null` if none is loaded. Always returns `200` — use this as a readiness probe. |
| `PUT` | `/project/` | Load or switch the active project. Body: `{"project_dir": "/path/to/project"}`. Returns `409` if a run is currently active. |

## Processes

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/processes/` | List available workflow processes |
| `GET` | `/processes/{name}/schema` | JSON schema for a process config |
| `GET` | `/processes/{name}/source` | Full source code of a process file |

Process schemas include JSON-compatible defaults. Defaults stored as custom
validated Python types are serialized through their configured Pydantic field
serializer before being returned.

## Protocols

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/protocols/` | List saved protocol files |
| `GET` | `/protocols/{filename}` | Read a protocol file by filename |
| `POST` | `/protocols/` | Save a new versioned protocol file |
| `DELETE` | `/protocols/{filename}` | Permanently delete a protocol file |

Protocol names may not contain the characters `/ \ : ? # * < > |`. Names are
stored as `{name}_{YYYY-MM-DDTHH-MM-SS}.json` in `protocols_historic/`.

## Run control

Only one run can be active at a time (the physical platform enforces this constraint). Starting a second run while one is active returns HTTP `409`.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/run/` | Start a workflow run from a protocol file. Body: `{"protocol": "<filename>", "dry_run": false}`. `protocol` is required; `dry_run` defaults to `false`. Returns HTTP `202` with a derived `run_id`, `409` if a run is already active, or `422` if `record_monitoring: true` was passed with no monitoring variables registered (the run never starts). Pass `record_monitoring: true` to also persist every monitored variable's readings for this run — see [Monitoring](#monitoring). |
| `GET` | `/run/active` | Return `{"active_run_id": ..., "state": ..., "pending_inputs": {...}, "protocol": ...}` without consuming queued events. `state` is `"running"` or `"paused"` while active, `null` if no run is active. `pending_inputs` maps `node_id -> prompt message` for every node currently blocked on `request_operator_input()` — lets a reconnecting dashboard client redraw an open prompt it missed on the live stream. `protocol` is the filename the active run was started from, so a client that didn't itself start the run can rebuild the process/node view before replaying events. |
| `GET` | `/run/status` | Poll the current run state and events. Query param `after` (default `0`) is a cursor — returns every event recorded from that index onward plus a `cursor` field to pass as `after` next time. The read is non-destructive: any number of independent callers can poll concurrently, each tracking its own cursor, without stealing events from one another; `after=0` (or omitted) replays the full history. States are `running`, `paused`, and the terminal `finished`, `failed`, `cancelled`. `reason` says why a `cancelled` run was stopped when whoever stopped it gave one — a safety interlock calling [`MonitoringContext.stop_run(reason)`](#custom-sources), say — and is `null` otherwise, including after `DELETE /run/`. Returns `404` if no run has been recorded. |
| `GET` | `/run/report` | Full execution report for the current or last run, with the same `reason` as `/run/status`. Returns `202` if the run has not finished yet (including while paused). |
| `DELETE` | `/run/` | Cancel the active run. Sends a cooperative cancellation signal — the current in-flight device call completes, then execution stops at the next step checkpoint. Works from either `running` or `paused`. Also wakes any node currently blocked on `request_operator_input()`. Returns `404` if no run is active. |
| `POST` | `/run/pause` | Pause the active run. Sends a cooperative pause signal — execution holds at the next checkpoint, which may be between individual device calls inside a node, not just between nodes. The physical hardware is left in whatever state it reached; nothing is moved to a "safe" position. Only valid from `running`. Returns `404` if no run is active, `409` if not currently running. |
| `POST` | `/run/resume` | Resume a paused run, continuing execution from exactly where it held. Only valid from `paused`. Returns `404` if no run is active, `409` if not currently paused. |
| `POST` | `/run/input` | Answer a pending `request_operator_input()` prompt. Body: `{"node_id": "...", "value": "..."}`. Returns `204`, or `404` if that node isn't currently waiting for a reply — either it never asked, already got an answer, timed out, or the run ended. |
| `GET` | `/run/stream` | Stream workflow events as Server-Sent Events (SSE). A connection opened after the run started first replays every event recorded so far, then continues live — each connection tracks its own position, so multiple dashboard viewers can stream the same run concurrently and each gets the full history. Pushes a `{"state": "paused"\|"running"}` frame on pause/resume without closing the connection, then closes with a terminal-state frame when the run ends. |
| `GET` | `/run/pool` | Drain pending device commands and delete their pool files; returns an empty list when no commands are pending. |

The derived `run_id` has the format `{protocol_stem}_{YYYY-MM-DDTHH-MM-SS}` and is returned in the `POST /run/` response. It is human-readable and tied to the protocol name and start time.

Example `POST /run/` request:

```json
{
  "protocol": "suzuki_batch_2026-01-15T09-30-00.json",
  "dry_run": false,
  "error_resilient": false,
  "record_monitoring": false
}
```

Use `dry_run: true` to simulate device calls. The workflow graph and node logic still run, but physical HTTP calls are suppressed.

`POST /run/` accepts `timeout_commands` in the JSON body. Use values such as
`"5 s"` or `"2 min"` to control feedback polling timeout; omit it for the
default `"10 s"`, or pass `""` to poll without a timeout.

Set `error_resilient: true` to allow client-side errors (HTTP failures, timeouts) to be logged without stopping the entire run. Each node's commands still run to completion; the node is marked `FAILED` and its successors become `INACTIVE`, but independent branches continue normally. Defaults to `false`.

Set `record_monitoring: true` to force monitoring on for the run's duration and persist every reading to `log/monitoring/{run_id}/`, using whatever variables are currently registered via `PUT /monitoring/config`. If no variables are registered, the request fails with `422` and the run never starts — it does not start silently and record nothing. See [Monitoring](#monitoring).

When a node calls `ctx.request_operator_input(message, timeout_seconds)`, the executor emits `NODE_INPUT_REQUESTED` (`message` is the prompt) and that node's worker thread blocks — other nodes keep running. Reply with `POST /run/input` using the same `node_id`; the executor then emits `NODE_INPUT_RECEIVED` (`input_value` is the reply) and the node resumes with that value. If nobody replies before `timeout_seconds` elapses, the node fails instead of waiting forever. See [Concepts → Human-in-the-Loop Input](concepts.md#human-in-the-loop-input).

### Event schema (`/run/status` and `/run/stream`)

Both `GET /run/status` (`events` array) and `GET /run/stream` (one SSE `data:` frame per event) carry the same `WorkflowExecutionEvent` JSON shape:

| Field | Type | Description |
|-------|------|-------------|
| `event_type` | string | One of `EXECUTION_STARTED`, `ITERATION_STARTED`, `NODE_WAITING`, `NODE_RUNNING`, `NODE_PROGRESS`, `NODE_INPUT_REQUESTED`, `NODE_INPUT_RECEIVED`, `NODE_COMPLETED`, `NODE_INACTIVE`, `NODE_FAILED`, `LOOPBACK_TRIGGERED`, `EXECUTION_FINISHED` |
| `message` | string | Human-readable status for this event |
| `process` | string \| null | The process step key, e.g. `"clean_0"` |
| `node_key` | `[node_id, iteration]` \| null | Identifies the node; `null` for process-level events (`EXECUTION_STARTED`/`EXECUTION_FINISHED`) |
| `state` | string \| null | `NodeState` at the time of the event (`WAITING`, `RUNNING`, `COMPLETED`, `INACTIVE`, `FAILED`) |
| `result` | bool \| null | Node's return value, once known |
| `method` | string \| null | Name of the node method being executed |
| `percentage` | int \| null | `0`–`100`. Auto-managed (`0` on `NODE_RUNNING`, `100` on `NODE_COMPLETED`) unless the node calls `ctx.report_progress(...)`, which emits its own `NODE_PROGRESS` event with the reported value — see [Concepts → Node Progress Feedback](concepts.md#node-progress-feedback) |
| `source` / `target` | string \| null | Set on `LOOPBACK_TRIGGERED` events |
| `active_predecessor_count` / `completed_predecessor_count` | int \| null | Predecessor bookkeeping for waiting nodes |
| `wait_seconds` | float \| null | Set only when the node calls `ctx.report_progress(percentage, message, wait_seconds=N)`; a fire-once hint (not persisted run history) for clients to render a live countdown anchored to `timestamp`. `null` on every other event, which signals the countdown should be cleared |
| `input_value` | string \| null | Set only on `NODE_INPUT_RECEIVED` — the operator's reply delivered via `POST /run/input`. `null` on every other event, including `NODE_INPUT_REQUESTED` (the prompt text itself is carried in `message`) |
| `timestamp` | float | Unix timestamp |

`GET /run/stream` also emits non-`WorkflowExecutionEvent` `{"state": ...}` frames: a mid-stream `{"state": "paused"}` / `{"state": "running"}` pair on pause/resume (connection stays open — pausing doesn't produce a `WorkflowExecutionEvent` since nothing in the executor runs when the state flips), and a final one that closes the stream: `{"state": "finished" | "failed" | "cancelled"}` — `{"state": "cancelled", "reason": "..."}` for a run stopped with a reason (see `/run/status`).

To render live per-node feedback (progress bar + message), group events by `node_key` — every event that carries one (`NODE_WAITING`, `NODE_RUNNING`, `NODE_PROGRESS`, `NODE_INPUT_REQUESTED`, `NODE_INPUT_RECEIVED`, `NODE_COMPLETED`, `NODE_INACTIVE`, `NODE_FAILED`) updates that node's latest `state`, `percentage`, and `message` in place. This is exactly what the bundled dashboard's Run Control page does — see [HTML UI → Live node progress](html-ui.md#live-node-progress) and [HTML UI → Operator input prompts](html-ui.md#operator-input-prompts).

## Logs

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/logs/` | List log file metadata, sorted most recent first |
| `GET` | `/logs/search?query=...&max_results=50` | Search all active log files for matching lines, case-insensitive |
| `GET` | `/logs/{filename}?tail=N` | Read a log file. `tail` is optional and returns only the last `N` lines. |

## Components

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/components/` | Return the full `associations.json` map |
| `GET` | `/components/ping?timeout=2.0` | Check reachability of every device URL |

## Monitoring

A single, project-wide sensor-polling toggle — there is no session id. Config is persisted to `connectivity/monitoring.json`. Live readings are kept in a bounded in-memory buffer (a fixed cap per variable); nothing is written to disk unless a protocol run opts in via `record_monitoring: true` (see [Run control](#run-control)), in which case readings are persisted to `log/monitoring/{run_id}/` for that run's duration.

Monitoring turns on in one of two ways:
- **Manually** — `POST /monitoring/start` / `POST /monitoring/stop`. This toggle also makes the [live platform view](#live-platform-view) live, so it works with no variables registered, and during a run: it then only sets `manual_on`, polling continues for the run either way, and `manual_on` decides whether monitoring stays on after it.
- **Automatically** — a protocol run started with `record_monitoring: true` (or any run, if monitoring was already manually on) forces monitoring on for its duration; control reverts to whatever the manual setting is once the run ends.

Readings are keyed by device, command and parameters: `pump::value` for a variable without parameters, `adc::read::{"channel":2}` (the parameters as JSON with sorted keys and no spaces) otherwise. Two variables on one command with different parameters keep their own readings.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/monitoring/discover/{component}` | List GET commands a component exposes, read from the device server's live OpenAPI schema |
| `GET` | `/monitoring/config` | Return the current monitoring registration (`sample_time`, `request_timeout`, `variables`) |
| `PUT` | `/monitoring/config` | Register which variables to poll and how often. Does not start polling. |
| `GET` | `/monitoring/state` | Return `{manual_on, run_active, recording, run_id, effective_on}` |
| `POST` | `/monitoring/start` | Turn monitoring on manually; the platform view goes live. During a run only `manual_on` changes. Idempotent if already on. |
| `POST` | `/monitoring/stop` | Turn monitoring off manually; the platform view stops being live. During a run only `manual_on` changes, and polling stops when the run ends. Idempotent if already off. |
| `GET` | `/monitoring/latest` | Latest reading per registered variable, by key — the live dashboard feed. `{}` if nothing has been polled yet. |
| `GET` | `/monitoring/history/{component}/{command}` | Bounded in-memory reading history for one variable, most recent last. For a variable with parameters, add `?kwargs={"channel": 2}` (JSON). `[]` for a variable that hasn't been polled yet — never `404`. |
| `GET` | `/monitoring/recordings/{run_id}/{component}/{command}` | Full recorded time-series for one variable from a past run started with `record_monitoring: true`. Pass `?tail=N` for the last N readings, and `?kwargs=` as for the history. `404` if that run never recorded this variable. |

### Custom sources

`component: "custom"` is a reserved pseudo-device for readings computed in Python instead of polled from a real device. Its "commands" are function names registered in `{project_dir}/customizations/monitoring/monitoring_hook.py`:

```python
# customizations/monitoring/monitoring_hook.py
CUSTOM_SOURCES: dict[str, Callable[..., Any]] = {
    "reactor_fill_pct": lambda **kwargs: 42.0,
}
```

Register and poll it exactly like a real variable — `{"component": "custom", "command": "reactor_fill_pct", "kwargs": {...}}` in `PUT /monitoring/config`. `GET /monitoring/discover/custom` lists the registered function names instead of querying a device. Each distinct custom source polls independently and never shares a poll-tick worker with a real component or a different custom source; a broken or missing hook file, or a raised exception inside a registered function, shows up as `error` on that reading and never stops the rest of the poll tick. The file is optional and reloaded fresh each time monitoring turns on, so edits take effect on the next start without a server restart.

A registered function can read a real device by importing `MonitoringContext` and reading `MonitoringContext.platform` — the exact `Platform` (and its `ComponentClient` instances/locks) real-component readings use for that ON-cycle:

```python
from chemunited_workflow import MonitoringContext

def chiller_temperature_f():
    celsius = MonitoringContext.platform["chiller"].get("temperature")
    return celsius * 9 / 5 + 32
```

`MonitoringContext.platform` is `None` whenever no poll cycle is running. Reading a component another pool worker is mid-fetching in the same tick never deadlocks — `ComponentClient`'s per-device lock is non-blocking, so the loser gets a `ConcurrentClientAccessError` immediately, caught the same as any other exception raised inside a custom source and surfaced as that reading's `error`. Never call `.close()` or `.register()` on anything reached through `MonitoringContext.platform` — the poll loop owns its lifecycle for the whole ON-cycle. To unit-test a function that uses it, monkeypatch `MonitoringContext.platform` directly before calling the function.

A custom source can also act as a safety interlock. `MonitoringContext.stop_run(reason)` stops the active protocol run the same way the dashboard's Stop button (`DELETE /run/`) does — the run ends `cancelled` — and returns `True`, or returns `False` when no run is active. `reason` (optional) says why: it is reported with the cancelled run (`reason` on `/run/status` and `/run/report`, and on the closing frame of `/run/stream`), and the dashboard's Run Control page shows it in red as the run's outcome, where a plain cancel just reads "Run cancelled.". Monitoring is forced on for every run, so a check in a custom source runs on every tick of every run:

```python
from chemunited_workflow import MonitoringContext

def reactor_pressure():
    bar = MonitoringContext.platform["reactor"].get("pressure")
    if bar > 3.0 and MonitoringContext.stop_run(f"Overpressure: {bar} bar > 3.0 bar"):
        MonitoringContext.platform["feed_valve"].put("close")
        raise RuntimeError(f"Overpressure ({bar} bar): protocol stopped")
    return bar
```

Like `platform`, `stop_run()` is only wired up while a poll cycle runs inside the API server; anywhere else it returns `False`. To unit-test a function that uses it, set `MonitoringContext._stop_run` to a stand-in callable that takes the reason, such as `lambda reason: True`.

Example workflow:

```bash
# 1. (optional) discover what a component can expose
curl http://127.0.0.1:3116/monitoring/discover/reactor_01

# 2. register variables to monitor
curl -X PUT http://127.0.0.1:3116/monitoring/config \
  -H "Content-Type: application/json" \
  -d '{
    "sample_time": 5.0,
    "request_timeout": 5.0,
    "variables": [
      {"component": "reactor_01", "command": "temperature"},
      {"component": "pump_01",    "command": "flow_rate"}
    ]
  }'

# 3. turn monitoring on manually (optional — a recorded run turns it on automatically)
curl -X POST http://127.0.0.1:3116/monitoring/start
# → {"manual_on": true, "run_active": false, "recording": false, "run_id": null, "effective_on": true}

# 4. read live values
curl http://127.0.0.1:3116/monitoring/latest

# 5. read the bounded live history for one variable
curl http://127.0.0.1:3116/monitoring/history/reactor_01/temperature

# 6. stop monitoring
curl -X POST http://127.0.0.1:3116/monitoring/stop

# 7. start a protocol run that also records monitoring data
curl -X POST http://127.0.0.1:3116/run/ \
  -H "Content-Type: application/json" \
  -d '{"protocol": "suzuki_batch_2026-01-15T09-30-00.json", "record_monitoring": true}'
# → {"run_id": "suzuki_batch_2026-01-15T09-30-00_2026-08-19T10-00-00", "state": "running"}

# 8. after the run, read back its recorded profile for one variable
curl http://127.0.0.1:3116/monitoring/recordings/suzuki_batch_2026-01-15T09-30-00_2026-08-19T10-00-00/reactor_01/temperature
```

Each variable is polled concurrently using its own per-request timeout, so a hung device only delays its own reading. Recorded readings are stored as JSONL with one entry per tick: `{"tick": 0, "time": "...", "value": ..., "error": null}`, in `{component}__{command}.jsonl`, or `{component}__{command}__{params}.jsonl` for a variable with parameters (`adc__read__channel=2.jsonl`).

Every request to a device, from a run, a monitoring read or the device panel, takes that device's process-wide lock for the request only. A pump infusing for ten minutes still answers monitoring reads between its idle-wait polls. A command that can't get the lock within 10 s fails with "device busy"; a monitoring read that can't get it skips that tick and keeps the last reading.

## Live platform view

The work-server keeps the latest state of every device in memory, built from the commands it sends: from protocol runs, the device panel (`POST /components/commands/...`) and custom routes. Every device starts `unknown` when the project loads. Each PUT/POST marks its device `running` with that command, then `done` once the device client's usual wait for the device to finish returns, or `failed` if the request fails or the wait times out. The device panel doesn't wait for the device to finish, so its commands are marked `done` as soon as the device accepts them. GETs aren't recorded. Commands sent outside the work-server never show.

The view is **live** only while monitoring is on from the Monitoring page (`POST /monitoring/start`). A run doesn't make it live by itself. Device states are recorded either way but only sent while live.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/platform/state` | `{live, seq, pictures, devices, displays}`. `devices` maps each component to `{kind, status, command, picture, error}`, where `command` is `{name, params, at, run, node}` (`run` and `node` are `null` for a device-panel command). `devices` and `displays` are `{}` while not live. `503` if no project is loaded. |
| `GET` | `/platform/stream` | Server-Sent Events. The first frame is `event: snapshot` with the same body as `/platform/state`. Then each change is an `event: update` frame, `{"seq": 7, "devices": {"pump": {...}}}`, with `id: <epoch>-<seq>`. A new snapshot follows whenever `live` changes, the project is reloaded, or the stream falls further behind than the server's change log. After 5 s without other frames, an `event: heartbeat` frame arrives. |

With the `live` extra (`pip install chemunited-workflow[live]`, which adds chemunited-core), each command also updates the device's `picture`: `{"links": [[0, 3]]}` for a rotary valve (rotor slots: 1 is the top one, counting clockwise; 0 is the hub), `{"open": true}` for a solenoid valve, `{"position": 1}` for a 2-way solenoid valve, `{"active": true}` for an MFC, `{"channels": [true, null, ...]}` for a relay (`null`: not switched since the server started). A command the picture can't follow, such as an unknown command or a position the valve can't take, leaves the device `unknown` with the reason in `error`. The dashboard draws pictures where the desktop app's export says each part sits (`draw/platform-live.json`, served at `GET /project/platform-live` with `svg_matches`, which is false once `platform.svg` no longer matches it).

`displays` holds the LCD readouts placed in the desktop app (saved in `draw/platform-live.json` and re-read on `PUT /project`): `{"Inlet pressure": {"value": "1.02 bar", "at": "...", "error": null, "monitored": true}}`. Each shows the latest monitoring reading of its variable, as text. `monitored` is false when the variable isn't in the monitoring list; LCDs never read a device themselves.

A browser that reconnects sends `Last-Event-ID` automatically. The server then replays the updates it missed, or sends a new snapshot when they're no longer in its log, when the id belongs to an earlier server or project load, or when the panel wasn't live at that id.

```
id: 3f9c01ab-44
event: update
data: {"seq": 44, "devices": {"pump": {"kind": null, "status": "running", "picture": null, "error": null,
       "command": {"name": "infuse", "params": {"volume": "1 ml"}, "at": "2026-10-23T10:31:02.512",
                   "run": "dose_001_2026-10-23T10-30-55", "node": "start"}}}}
```

## Export

One row per executed run — the run's log file, its correlated monitoring recording (if any), and its source protocol (if it still exists) — that can be zipped up for download and/or permanently cleaned out of the project. Downloading and cleaning are two separate actions; downloading never deletes anything.

Rows are correlated purely by filename convention (there is no stored link): a log is written as `{protocol_stem}_executed_{timestamp}.log`, its monitoring recording lives at `log/monitoring/{protocol_stem}_{timestamp}/`, and its source protocol is `protocols_historic/{protocol_stem}.json`. A row only exists if its log file exists — a saved-but-never-run protocol produces no row, and a monitoring recording whose log was removed some other way is not shown. Because the same protocol can be run more than once, **the log filename is each row's identity**, not the protocol name.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/export/preview` | List every row: `{"log": {...}, "monitoring": {"run_id", "files": [...], "total_size_bytes"} \| null, "protocol": {...} \| null}`, most recently modified log first. |
| `GET` | `/export/download?log={filename}` | Zip the selected runs (repeat `log` for more than one) and return it as a file download (`Content-Disposition: attachment`). Never deletes anything. `422` if no `log` is given. |
| `POST` | `/export/clean` | Body `{"logs": ["{filename}", ...]}`. Permanently delete the selected runs' log files and monitoring recordings. Returns `{"deleted": [...], "count": N}`. `protocols_historic/` is never touched — a run's protocol is always copied into its export, never removed by clean. `422` if `logs` is empty. |

A zip's members are `log/{filename}`, `log/monitoring/{run_id}/{filename}`, and `protocols_historic/{filename}`. Selecting two runs of the same protocol writes that protocol file into the zip only once. An unknown or already-deleted filename passed to `download`/`clean` is skipped silently rather than erroring the whole request.

### Custom export behavior

The same extensibility shape as [custom routes](#custom-routes): an optional `{project_dir}/customizations/export/export_hook.py` can override `build_zip` and/or `clean` independently, via an `EXPORT_HOOKS` dict. Each hook receives the same selected log filenames the endpoint was called with:

```python
# customizations/export/export_hook.py
from pathlib import Path

def build_zip(project_dir: Path, logs: list[str]) -> bytes:
    ...  # build and return your own zip bytes for the selected runs

def clean(project_dir: Path, logs: list[str]) -> dict:
    ...  # delete whatever you like for the selected runs, return {"deleted": [...], "count": N}

EXPORT_HOOKS = {
    "build_zip": build_zip,  # optional — omit to keep the default zip contents
    "clean": clean,          # optional — omit to keep the default clean behavior
}
```

The file is optional and reloaded fresh on every call. A missing file or one that fails to import (or doesn't export an `EXPORT_HOOKS` dict) falls back to the default behavior for both actions — a broken hook file never breaks `/export/preview`, `/export/download`, or `/export/clean`. Once a hook function is found and called, though, its own exception is *not* swallowed — it comes back as HTTP `500`, so a buggy custom `clean()` never silently reports success (or silently falls back to deleting a different set of files than the one it promised).

See `examples/custom_project/customizations/export/` for a full working example.

## Custom routes

The same extensibility shape as [custom sources](#custom-sources), generalized to arbitrary named actions instead of monitored readings — a project can expose functions to the frontend and an LLM without a code change to `chemunited_workflow` itself. Functions are registered in `{project_dir}/customizations/routers/router_hook.py`:

```python
# customizations/routers/router_hook.py
CUSTOM_ROUTES: dict[str, Callable[..., Any]] = {
    "purge_reactor": purge_reactor,
}
```

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/custom/discover` | List registered route names, with parameter hints introspected from each function's signature |
| `POST` | `/custom/{name}` | Call a registered route by name; the request body is passed through as keyword arguments |

The file is optional and reloaded fresh on every call, so edits take effect immediately — no server restart, no "turning monitoring off and on" step needed. Calling an unregistered `name` returns `404`. A raised exception inside the registered function is not a `404`/`500` — it comes back as `{"name", "ok": false, "result": null, "error": "...", "latency_ms": ...}`, the same "the call itself succeeded, the action failed" contract `POST /components/commands/{component}/{command}` already uses for a device command.

A registered function can reach a real device by importing `CustomRouteContext` and reading `CustomRouteContext.platform` — a throwaway `Platform` opened just for that one call and closed once it returns (unlike `MonitoringContext`, which stays open for an entire monitoring poll cycle, this is scoped to a single call and never shared):

```python
from chemunited_workflow import CustomRouteContext

def purge_reactor(volume_ml: float) -> dict:
    platform = CustomRouteContext.platform
    platform["pump"].put("flow_rate", value=volume_ml)
    return {"status": "ok"}
```

`CustomRouteContext.platform` is `None` whenever no custom route call is currently in flight. Never call `.close()` or `.register()` on anything reached through it — the caller owns its lifecycle for the call's duration.

Example workflow:

```bash
# 1. discover what's registered
curl http://127.0.0.1:3116/custom/discover

# 2. call one, passing kwargs as the request body
curl -X POST http://127.0.0.1:3116/custom/purge_reactor \
  -H "Content-Type: application/json" \
  -d '{"volume_ml": 5.0}'
# → {"name": "purge_reactor", "ok": true, "result": {"status": "ok"}, "error": null, "latency_ms": 12}
```

See `examples/custom_project/customizations/routers/` for a full working example.

Visit `/docs` for the interactive Swagger UI, or `/` for the HTML dashboard.

---

[← Back to README](../README.md)
