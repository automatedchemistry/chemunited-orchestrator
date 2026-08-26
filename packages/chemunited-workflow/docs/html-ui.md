# HTML UI

> Requires the FastAPI server — see [Deployment Modes](deployment.md#fastapi-server).

When the FastAPI server is running, open `http://127.0.0.1:3116/` to access the browser-based dashboard. The UI is a single Vue single-page application whose built assets ship with the package (`chemunited_workflow/web/`) — no separate build step is required to use it.

| Page | URL | Description |
|------|-----|-------------|
| Dashboard | `/` | Active run status, protocol/process counts, platform device map, quick links |
| Run Control | `/run-control` | Start/pause/resume/cancel runs, live event feed via SSE, per-node progress bars |
| Protocols | `/protocols` | List and manage saved protocol files |
| Monitoring | `/monitoring` | Live sensor monitoring sessions and time-series profiles |
| Devices | `/devices` | Component connectivity map and ping check |
| Logs | `/logs` | Browse and tail log files |
| Export | `/export` | Download a zip of logs/monitoring/protocol history, and clean the source files out of the project |

Every route above is served by the same `index.html` (see `chemunited_workflow/api/routers/ui.py`); Vue Router handles client-side navigation between pages, and Pinia (`stores/runStatus.ts`) tracks shared run state across them.

## Live node progress

Run Control shows one card per process step (`clean_0`, `react_1`, ...). As a run reaches each node inside a process, a row for it appears in that card — incrementally, not all up front — with a progress bar and a status label:

- **Percentage** starts at `0%` when the node starts running and reaches `100%` on completion, even if the node never reports anything itself.
- **Message** is a live snapshot, not a log — it always shows whatever was reported most recently, and is replaced (not appended to) on the next update.
- A **failed** node's row turns red and keeps whatever percentage/message it last reported, instead of silently freezing mid-progress.
- A **wait countdown** (depleting clock + remaining time, e.g. `"5:00"` counting down to `0s`) appears next to the message when a node reports `wait_seconds`, and disappears the instant that node's next event arrives — the dashboard ticks it down client-side from the reported duration and the event's timestamp; the backend only sends the value once.

This comes entirely from the `node_key`-bearing events already described in [API Reference → Event schema](api-reference.md#event-schema-runstatus-and-runstream) — the dashboard doesn't poll anything extra for it. To get finer-grained bars than the automatic `0% → 100%` jump, node authors call `ctx.report_progress(percentage, message)` from inside a node method; see [Concepts → Node Progress Feedback](concepts.md#node-progress-feedback) for the authoring side.

If you build a custom dashboard (per-project override or fully independent), the same data is available from `GET /run/stream` or `GET /run/status` — group events by `node_key` the same way `RunControlView.vue` does (`.web-chemunited/src/views/RunControlView.vue`, `stores/runStatus.ts`).

## Operator input prompts

When a node calls `ctx.request_operator_input(message, timeout_seconds)` (see [Concepts → Human-in-the-Loop Input](concepts.md#human-in-the-loop-input)), that node's row on Run Control grows a small reply form — the prompt message, a text box, and a Reply button — in the same spot the progress bar and wait countdown live. Submitting it posts to `POST /run/input`; the run resumes once the reply is delivered, and the form disappears.

Reconnecting mid-wait (e.g. navigating back to Run Control after the live `NODE_INPUT_REQUESTED` event already streamed) still recovers the open prompt — `GET /run/active`'s `pending_inputs` field is read on mount and used to redraw it. This doesn't survive a full server restart: like the rest of run state, a pending prompt lives only in memory.

## Per-project override

A project can supply its own pre-built dashboard and the server will prefer it over the bundled one — no code changes to `chemunited_workflow` required. Drop a built SPA here:

```
{project_dir}/
└── customizations/
    └── ui/
        ├── dist/
        │   ├── index.html
        │   └── assets/
        │       ├── index-XXXXXXXX.js
        │       └── index-XXXXXXXX.css
        └── static/          # unrelated: served at /project-static/{filename}
```

Resolution happens per request, driven by whatever project is currently loaded (via `chemunited-workflow serve <project_dir>` or `PUT /project/`):

- `GET /`, `/run-control`, `/protocols`, `/monitoring`, `/devices`, `/logs`, `/export` serve `{project_dir}/customizations/ui/dist/index.html` if it exists, otherwise the bundled `chemunited_workflow/web/index.html`.
- `GET /assets/{filename}` looks in `{project_dir}/customizations/ui/dist/assets/` first, then falls back to the package's own `assets/`.

Your build must emit **root-absolute** asset URLs (`/assets/xyz.js`, not `./assets/xyz.js`) — this is Vite's default (no custom `base`), which is exactly what `.web-chemunited` itself uses, so pointing any Vite project's `outDir` at `{project_dir}/customizations/ui/dist` works with no extra config. Other bundlers work too as long as they emit the same root-absolute convention.

Two limitations to be aware of:

- The dashboard favicon (`/chemunited.ico`) always comes from the package — it isn't overridable.
- Only the seven page paths above are server-routed. A custom SPA should reuse those route names for anything that needs to survive a hard refresh or direct link; client-side navigation (`RouterLink`/`<a>` clicks handled by your app's router) works for any route without a server-side match.

## Modifying the bundled UI

To change the dashboard that ships as the package default (affects every project that doesn't supply its own override), edit the Vue source directly:

```bash
cd .web-chemunited
npm install      # first time only
npm run build
```

Source layout:

```
.web-chemunited/src/
├── App.vue              # shell: sidebar nav, theme toggle, notifications
├── router/index.ts       # route table
├── views/                # one file per page (DashboardView.vue, RunControlView.vue, ...)
├── components/           # shared components (DevicePropertiesPanel.vue, SchemaForm.vue)
├── stores/runStatus.ts   # Pinia store for active-run state
└── composables/          # e.g. useNotification.ts
```

Built assets are written to `chemunited_workflow/web/` automatically (configured in `vite.config.ts`) and are what `GET /` and the other page routes serve as a fallback.

If you need a dashboard that's genuinely independent of the package (own branding, own release cycle, no need to touch vendored source), build a separate frontend against the REST API instead — see [API Reference](api-reference.md). The API is not coupled to the bundled UI.

---

[← Back to README](../README.md)
