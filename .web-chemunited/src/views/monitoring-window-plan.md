# Monitoring Window Plan

## Summary

`MonitoringView.vue` is a single, session-less monitoring dashboard backed by the `/monitoring/*` endpoints described in `docs/api-reference.md`. There is no session id: the backend holds one project-wide on/off state (`GET /monitoring/state`), forced on automatically while a protocol run is active and reverting to the user's manual setting once the run ends.

Users configure `sample_time`, `request_timeout`, and GET variables before turning monitoring on. Once running, variable selection and config are locked until monitoring is turned off (or the active run finishes, if it was forced on). Numeric readings are plotted as time profiles; non-numeric readings are shown in table form because objects, strings, and arrays should not be plotted.

## Key Changes (superseding the original session-based design)

- Load initial page state from `GET /project/`, `GET /components/`, `GET /monitoring/config`, and `GET /monitoring/state`.
- **State polling**: a fixed-interval poll of `GET /monitoring/state` (independent of `sample_time`) runs continuously from `onMounted`, so the page detects a protocol run auto-starting monitoring while the user is already looking at it. On an off→on transition it seeds each variable's history and starts the reading-poll timer; on an on→off transition it stops the reading-poll timer.
- **Manual toggle**: a single Start/Stop button reflects `state.effective_on`. It's disabled while `state.run_active` is true (labeled "Auto (run active)") — the manual toggle isn't the user's to use while a protocol run has forced monitoring on; the backend also rejects `POST /monitoring/start`/`stop` with 409 in that case.
- Let users discover variables by selecting a component and calling `GET /monitoring/discover/{component}`.
  - `404` (component not found): show an inline "component not found" message next to the picker; do not block other picker interactions.
  - `502` (device unreachable / no OpenAPI schema): show an inline "device unreachable" message with the raw detail text; let the user pick a different component or retry.
- **Variable config form**: for each discovered GET command, let the user set `kwargs` via a key/value form built from `DiscoveredCommand.parameters` (falling back to a raw JSON textarea when parameters are absent/unstructured). Also expose `sample_time` and `request_timeout` as top-level fields on the same form, since both are part of `MonitoringConfig`.
- Persist selected variables and config with `PUT /monitoring/config` before `POST /monitoring/start`.
  - **Non-atomic start**: if `PUT /monitoring/config` succeeds but `POST /monitoring/start` then fails (e.g. `422` no variables, or `409` a run raced to force monitoring on in between), leave the form unlocked (config is already persisted and harmless at rest) and show the error inline with a retry action that re-issues `POST /monitoring/start` only, without re-submitting config.
- Turn monitoring off with `POST /monitoring/stop` and unlock edits afterward.
- **Fetch strategy while running**:
  - Poll interval = `max(config.sample_time, 1)` seconds, capped at a sane minimum so a very small `sample_time` doesn't hammer the API.
  - Each tick: call `GET /monitoring/latest` only (one request regardless of variable count) — no session id in the URL.
  - Per numeric variable, fetch `GET /monitoring/history/{component}/{command}` exactly once, when the panel first turns on (either on page load or right after Start/an auto-on transition) — not on every tick. The backend already caps this history server-side (see `HISTORY_MAXLEN` in `monitoring_store.py`), so no `tail` query param or client-side authoritative cap is needed; readings from `/latest` are appended client-side to that variable's in-memory point buffer as a defensive trim only.
  - On `visibilitychange` back to `visible` after the tab was hidden (where `setInterval` throttling may have caused missed ticks), re-fetch the full history once for each numeric variable to correct any gap, then resume incremental polling.

## Display Behavior

- Each selected variable gets one monitoring panel with component, command, status, latest timestamp, and latest value.
- **Display mode is pinned per variable**, decided once from the first reading with a non-null `value` and no `error` (from the initial history fetch or the first `/latest` poll), and does not change for the rest of the time monitoring is on. This avoids a panel flipping between chart and table as `value`'s type varies tick to tick.
- Numeric values:
  - Render a compact inline SVG time-series chart from the client-side point buffer described above.
- Non-numeric values:
  - Do not render a chart.
  - Render history as a table with `tick`, `time`, `value`, and `error`.
  - Show plain strings/numbers/booleans directly.
  - Show flat objects as key/value rows where useful.
  - Show arrays or nested objects as formatted JSON inside the value cell.
- Error readings:
  - Keep the variable panel visible.
  - Show the error message in the latest-value area and in the history table.
  - Exclude errored readings from numeric chart points.
- **Recording indicator**: a "Recording" pill (with the active `run_id`) is shown whenever `state.recording` is true, so the user can tell readings are also being persisted to `log/monitoring/{run_id}/` for the active run.

## API / Types

No backend changes are required beyond what's in `docs/api-reference.md`.

Frontend types inside `MonitoringView.vue`:

- `MonitoringVariable`: `{ component: string; command: string; kwargs: Record<string, unknown> }`
- `MonitoringConfig`: `{ sample_time: number; request_timeout: number; variables: MonitoringVariable[] }`
- `MonitoringState`: `{ manual_on: boolean; run_active: boolean; recording: boolean; run_id: string | null; effective_on: boolean }`
- `MonitoringReading`: `{ tick: number; time: string; value: unknown; error: string | null }`
- `DiscoveredCommand`: `{ command: string; summary?: string; parameters?: unknown[] }`

## Test Plan

- Verify page states: loading, no project, project loaded with no variables, monitoring on, monitoring off, API error.
- Verify discovery loads GET commands and handles `404`/`502` with an inline, non-blocking message.
- Verify variables can be added/removed before turning monitoring on and cannot be edited while it's on.
- Verify `sample_time`/`request_timeout` are editable while off and locked while on.
- Verify start calls `PUT /monitoring/config` then `POST /monitoring/start`, and that a `POST` failure after a successful `PUT` leaves the form unlocked with a retry action.
- Verify the Start/Stop toggle reflects `state.effective_on`, is disabled with an "Auto (run active)" label while `state.run_active` is true, and that `POST /monitoring/start`/`stop` return 409 in that state.
- Verify the periodic `/monitoring/state` poll detects an externally-triggered on→off or off→on transition (e.g. a protocol run starting or finishing) and seeds/stops the reading-poll timer accordingly.
- Verify polling only calls `/latest` per tick, and `/history` is fetched once per variable when monitoring turns on (not once per tick) — assert request counts over several simulated ticks.
- Verify numeric profiles render charts; non-numeric profiles render tables and never attempt to chart.
- Verify display mode is pinned from the first valid reading and does not change if a later reading's type differs.
- Verify both timers (reading poll and state poll) are cleared on component unmount.
- Verify the "Recording" pill appears only when `state.recording` is true and shows the current `run_id`.
- Run frontend type-check/build for `.web-chemunited`.

## Assumptions

- Monitoring is a single, project-wide toggle — there is no way to have more than one thing "running" at once, so there's no session-conflict UI to build.
- Charts use inline SVG with no new dependency.
- Runtime type detection decides the display mode per variable from the first valid (non-null, non-error) history/latest value, then stays pinned until monitoring turns off.
- No request authentication/authorization exists anywhere else in this API today; start/stop access control is out of scope for this plan and would be an application-wide concern, not specific to monitoring.
