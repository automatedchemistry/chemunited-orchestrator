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
| Export | `/export` | Download a zip of runs' logs, manifests (the protocol that ran and the project's git commit), monitoring recordings and protocols, and clean the source files out of the project |
| Customizations | `/customizations` | Shown when the project customizes the dashboard: problems in `ui_hook.py`, a compile check of every custom page and widget, and what is applied where (see [Runtime customizations](#runtime-customizations)) |

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

## Stop reasons

A run stopped with a reason — a safety interlock in a custom monitoring source calling `MonitoringContext.stop_run(reason)`, see [API Reference → Custom sources](api-reference.md#custom-sources) — still ends `cancelled`, but Run Control shows it as an error: a red **Stopped** state with the reason as its caption, a `Run stopped: <reason>` message, and the reason on the interrupted process card in place of the generic "Run was cancelled.". The navigation dot and the Dashboard's last-run card turn red too. A plain cancel (the Cancel Run button, `DELETE /run/`) has no reason and keeps the grey **Cancelled**.

The reason arrives on the closing frame of `GET /run/stream`, and is read back from `GET /run/report` on page load, so reloading or coming back to Run Control after the stop still shows it.

## Runtime customizations

A project changes the bundled dashboard with files in `{project_dir}/customizations/ui/`, and nothing is built: the server reads `ui_hook.py`, and the browser compiles the `.vue` files when it loads them. Editing a file and reloading the page is the whole workflow, so a machine with only Python and pip can customize the dashboard. Updates to the dashboard itself still arrive with `pip install -U chemunited-workflow`.

```text
customizations/ui/
├── ui_hook.py      DASHBOARD = Dashboard(...)
├── theme.css       colour tokens (optional)
├── pages/          custom pages (.vue)
├── widgets/        widgets for slots on built-in pages (.vue)
├── components/     parts shared by pages and widgets (.vue, .js)
├── vendor/         single-file browser builds of libraries (.js)
└── assets/         icons and logos
```

Only `ui_hook.py` is required; the folder names are conventions. Start with `chemunited-workflow ui init <project_dir>`, which creates the hook, an example page, a theme, editor types and a lint config without touching existing files. `examples/custom_project/customizations/ui/` is a working example.

### `ui_hook.py`

```python
from chemunited_workflow.ui import (
    ActionField,
    Brand,
    Dashboard,
    HtmlPage,
    NavItem,
    PageAction,
    ProtocolsPage,
    VuePage,
    Widget,
)

DASHBOARD = Dashboard(
    brand=Brand(
        title="Auto Glycan Assembly",
        subtitle="Protocol Execution Layers",
        monogram="AGA",
    ),
    theme_css="theme.css",
    pages=[
        VuePage(
            path="/sensors",
            label="Sensors",
            component="pages/SensorsView.vue",
            icon="assets/sensors.svg",
            after="/monitoring",
        ),
        HtmlPage(
            path="/report", label="Report", render=build_report, refresh_seconds=30
        ),
    ],
    nav=[NavItem(path="/logs", label="Run logs")],
    actions=[
        PageAction(
            page="export",
            route="save_to_chemotion",
            label="Save to Chemotion",
            context={"logs": "selection"},
            fields=[ActionField("username", label="Chemotion username", remember=True)],
        ),
    ],
    widgets=[Widget(slot="dashboard.cards", component="widgets/ReactorCard.vue")],
    protocols=ProtocolsPage(
        process_categories={"command_": "Commands", "module_": "Modules"},
        other_label="Processes",
    ),
)
```

File paths are relative to `customizations/ui/`.

| Entry | What it does |
|-------|--------------|
| `Brand(title, subtitle, monogram, logo)` | The sidebar's brand block and the browser tab's title. `logo` (an image file) wins over `monogram` (up to 4 letters). |
| `theme_css` | A plain CSS file loaded after the dashboard's own. Override any of the 21 `--color-*` tokens of `.web-chemunited/src/assets/base.css`, on `:root` for the light theme and on `:root[data-theme='dark']` for the dark one. |
| `VuePage(path, label, component, icon, after, hidden, replaces)` | A page from a `.vue` file, with a nav entry placed after the entry named by `after` (at the end otherwise). `hidden=True` keeps it out of the nav; `replaces=True` takes over a built-in page's path and nav entry. |
| `HtmlPage(path, label, render, refresh_seconds, ...)` | A page whose HTML a Python function returns (Jinja2, `DataFrame.to_html()`, matplotlib SVG, Plotly), shown in a sandboxed frame, reloaded every `refresh_seconds` if set. No JavaScript needed. |
| `NavItem(path, label, hidden, order, icon)` | Rename, hide, move or re-icon a built-in nav entry. Built-in entries have orders 10, 20, ... 70. |
| `PageAction(page, route, label, icon, context, fields, confirm, refresh)` | A button on a built-in page that calls a function from `customizations/routers/router_hook.py`. `context` maps the function's parameters to values the page provides; its other parameters become form fields typed from the function's type hints. `confirm` asks first; `refresh` reloads the page's data afterwards. |
| `ActionField(name, label, placeholder, remember, hidden)` | How one parameter shows in an action's form. `remember` keeps the last value in the browser; `hidden` leaves it to its default. |
| `Widget(slot, component, title, order)` | A `.vue` component placed in a slot of a built-in page (below). It gets the slot's `context` as a prop. |
| `ProtocolsPage(process_categories, other_label)` | Tabs over the Protocols page's process library, grouping processes by name prefix; processes matching no prefix go under `other_label`. |

A custom page's path is one lowercase segment (`/sensors`); paths the server uses (`/ui`, `/run`, `/custom`, ...) are refused, and built-in page paths need `replaces=True`. Page URLs survive a hard refresh.

What each page passes to its actions (`context`) and where widgets go:

| Action page | Context |
|-------------|---------|
| `dashboard` | `project_dir` |
| `run-control` | `run_id`, `run_state` |
| `devices` | `components` (component names) |
| `export` | `selection` (the selected log filenames) |

| Slot | Where | Context |
|------|-------|---------|
| `dashboard.cards` | Below the Dashboard's summary cards | `project_dir`, `run_id`, `run_state` |
| `device.panel` | In the device panel opened from the Dashboard's platform picture | `device` (`id`, `label`, `figure`) |
| `run-control.panels` | Below Run Control's controls | `run_id`, `run_state` |
| `devices.panels` | Below the Devices connectivity map | `components` |

Every entry is checked when the hook loads. A problem (a missing file, an unknown route or slot, a typo in a field) is reported on the Customizations page and skips only that entry.

### Writing pages and widgets

Pages and widgets are ordinary Vue single-file components:

```vue
<script setup lang="ts">
import { ref } from 'vue'
import { attempt, callCustomRoute } from 'chemunited'
import Gauge from '../components/Gauge.vue'

const minutes = ref<number | null>(null)

async function calculate() {
  minutes.value = await attempt(
    () => callCustomRoute<number>('residence_time_min', { flow_rate_ml_min: 0.5, reactor_volume_ml: 10 }),
    { error: 'Could not calculate' },
  ) ?? null
}
</script>

<template>
  <div class="page-shell">
    <Gauge :value="minutes" />
    <button class="cu-button primary" @click="calculate">Calculate</button>
  </div>
</template>

<style scoped>
/* plain CSS */
</style>
```

- **Supported:** `<script setup>` and `<script>`, `lang="ts"` (types are stripped, not checked), `<style scoped>`, `v-bind()` in CSS, and relative imports of `.vue`, `.js` and `.css` files.
- **Importable by name:** `vue`, `vue-router`, `pinia` and `chemunited` only; they are the dashboard's own instances.
- **Libraries:** put a single-file browser build (ESM) under `vendor/` and import it by relative path (`import * as echarts from '../vendor/echarts.esm.min.js'`). Files under a `vendor/` folder load untouched.
- **Not supported:** `lang="scss|less|stylus"` or other preprocessors, `<style module>`, `src="..."` blocks, other bare npm imports, `defineProps<T>()` with `T` imported from another file (local types work), JSX.

The `chemunited` module:

| Export | What it is |
|--------|------------|
| `api.get/post/put/delete(url, body?)` | JSON requests to the REST API; failures throw an `ApiError` with the server's message. Writes carry the API token set in the sidebar. |
| `callCustomRoute(name, kwargs)` | Calls a `router_hook.py` function and returns its result; throws `ApiError` if the function raises. |
| `attempt(work, { success?, error? })` | Runs `work`, shows a notification on failure (and on success when `success` is given), never throws. |
| `notify(message, type)` | The dashboard's notification bar. |
| `useRunStatus()` | `runId`, `runState`, `stopReason` (computed) and `refresh()`. |
| `usePlatformLive()` | Live device and LCD state from `/platform/stream`; call `start()`. |
| `SchemaForm` | The dashboard's form for a map of JSON-schema-like properties. |
| `extUrl(path)`, `errorMessage(error)`, `version` | The URL of a file under `customizations/ui/`; an error's message; the UI API version. |

For a consistent look, pages can use the dashboard's classes: `page-shell`, `page-header`, `page-eyebrow`, `page-title`, `page-description`, and the stable `cu-panel`, `cu-panel-title`, `cu-muted`, `cu-button` (`primary`, `danger`) and `cu-input`, plus the `--color-*` tokens.

Keep pages thin: **pages show data and call Python; Python decides and validates.** Anything that drives hardware should go through a custom route, which can validate its arguments (for example with Pydantic) and be type-checked with mypy or pyright. Ad-hoc device commands go straight to the device's server and chemunited-workflow doesn't check them.

### Checking your work

Nothing type-checks a page before it runs, so the dashboard catches problems where they happen:

- A page or widget that fails to compile, load or run shows an error card with the file and line in its place. The rest of the dashboard, and any running experiment, are unaffected.
- The **Customizations** page lists the problems in `ui_hook.py`, compiles every declared `.vue` file, and shows what is applied where.
- `chemunited-workflow ui check <project_dir>` checks `ui_hook.py` and the files it names and, with `pip install "chemunited-workflow[ui-lint]"`, lints the `.vue` and `.js` files with oxlint. It exits with status 1 on problems.
- For type errors while editing, open `customizations/ui/` in an editor that reads `tsconfig.json`, such as VS Code with the Vue extension: `ui init` puts declarations for `vue` and `chemunited` under `types/`, so no Node install is needed. Rerun `ui init` after upgrading to refresh them.

### How it works

At start-up the dashboard fetches `GET /ui/manifest` and applies the brand, theme, nav and routes before its first render. When a custom page or widget is first shown, the dashboard loads its compiler, Vue's own `compiler-sfc` (the same version as the dashboard's Vue) plus sucrase to strip TypeScript, as a separate download of about 1 MB (300 KB compressed). Projects without `.vue` files never download it. Each file is fetched from `GET /ui/ext/...`, compiled, and its imports rewritten to the dashboard's shared modules; files are revalidated by ETag, so unchanged ones are neither downloaded nor compiled again.

Custom pages run with the dashboard's rights in the viewer's browser, the same trust level as `router_hook.py`, which already runs arbitrary Python on the server. Writes still need loopback or the API token. Pages rendered by `HtmlPage` run sandboxed, with no access to the dashboard. Like the rest of the read-only API, the files under `customizations/ui/` are readable by anyone who can open the dashboard (Python files excepted), so keep secrets in the Python hooks.

If `customizations/ui/dist/index.html` exists (below), it replaces the whole dashboard and `ui_hook.py` is not applied; the Customizations page says so.

## Per-project override

A project that has a build tool can instead replace the whole dashboard with its own pre-built app, and the server will prefer it over the bundled one — no code changes to `chemunited_workflow` required. Unlike [runtime customizations](#runtime-customizations), this needs Node (or another bundler) wherever the app is changed, and the project then owns the entire dashboard, so it doesn't get the bundled one's updates. Drop a built SPA here:

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

Built assets are written to `chemunited_workflow/web/` automatically (configured in `vite.config.ts`) and are what `GET /` and the other page routes serve as a fallback. The build also type-checks that `types/chemunited.d.ts` matches the `chemunited` module customizations import (`src/extensions/publicApi.ts`), and copies it with Vue's type declarations to `chemunited_workflow/ui/types/` for `chemunited-workflow ui init`.

The runtime customization code lives in `src/extensions/`: `bootstrap.ts` applies the manifest, `loader/` compiles `.vue` files in the browser (a lazy chunk), and `ExtensionHost.vue`, `ExtensionSlot.vue` and `PageActions.vue` host customizations on built-in pages. The `chemunited` module (`publicApi.ts`), the manifest schema and the `cu-*` classes (`src/assets/extensions.css`) are public UI API (`UI_API_VERSION`): within a version they only gain additions.

If you need a dashboard that's genuinely independent of the package (own branding, own release cycle, no need to touch vendored source), build a separate frontend against the REST API instead — see [API Reference](api-reference.md). The API is not coupled to the bundled UI.

---

[← Back to README](../README.md)
