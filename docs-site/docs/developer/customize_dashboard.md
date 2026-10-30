# Customize dashboard

The browser [dashboard](../dashboard/overview.md) (Dashboard, Run Control, Protocols, Monitoring, Devices, Logs,
Export) is a Vue single-page app served by the work-server (`chemunited-workflow`). A project can change it in two
ways:

* **Runtime customizations** (below): files in `customizations/ui/`, applied by the dashboard as it loads. Nothing is
  built, so a machine with only Python and pip can customize the dashboard, and the project keeps getting the
  dashboard's updates.
* **A full override**: the project ships its own pre-built app in `customizations/ui/dist/`. This needs Node or
  another bundler wherever the app is changed.

## Runtime customizations

Create the folder with:

```bash
chemunited-workflow ui init my_project/
```

```text
my_project/customizations/ui/
├── ui_hook.py      DASHBOARD = Dashboard(...): brand, pages, actions, widgets
├── theme.css       colour tokens
├── pages/          custom pages (.vue files)
├── types/          declarations for editors (refreshed by ui init)
└── tsconfig.json   lets VS Code check your .vue files as you type
```

Edit any file and reload the dashboard. `ui_hook.py` declares what changes:

```python
from chemunited_workflow.ui import (
    ActionField,
    Brand,
    Dashboard,
    PageAction,
    VuePage,
    Widget,
)

DASHBOARD = Dashboard(
    brand=Brand(title="Flow Synthesis Lab", monogram="FSL"),
    theme_css="theme.css",
    pages=[
        VuePage(
            path="/reactor",
            label="Reactor",
            component="pages/ReactorPage.vue",
            after="/monitoring",
        )
    ],
    actions=[
        PageAction(
            page="export",
            route="summarize_runs",
            label="Summarize",
            context={"logs": "selection"},
            fields=[ActionField("note", remember=True)],
        ),
    ],
    widgets=[Widget(slot="dashboard.cards", component="widgets/RunCard.vue")],
)
```

What a project can do this way:

| Written in | What it can do |
|------------|----------------|
| Python (`ui_hook.py`) | Rebrand the sidebar, recolour the dashboard (`theme.css`), add, rename, hide or reorder nav entries, group the Protocols page's processes into tabs, and add buttons to built-in pages that call your Python functions in `customizations/routers/router_hook.py`, with forms built from their type hints |
| Python (`HtmlPage`) | Pages whose HTML a Python function returns: tables, matplotlib or Plotly charts, reports |
| `.vue` files | Any page or widget a Vue component can be, using the dashboard's API helpers, live run and device state, and single-file browser builds of libraries such as ECharts or Chart.js |

<div class="info-block">
<strong>💡 Note</strong><br>
Without Node, <code>.vue</code> files can't use npm packages, Sass or other preprocessors, and nothing type-checks a
page before it runs. A page that fails shows an error card with the file and line instead, and the dashboard's
<strong>Customizations</strong> page compiles every file and lists the problems. <code>chemunited-workflow ui check
my_project/</code> checks <code>ui_hook.py</code> and, with <code>pip install "chemunited-workflow[ui-lint]"</code>,
lints the files.
</div>

Keep pages thin: pages show data and call Python, and Python decides and validates. Anything that drives hardware
belongs in a `router_hook.py` function.

`examples/custom_project/customizations/ui/` in `chemunited-workflow` is a working example, and the package's
`docs/html-ui.md` is the full reference: every `ui_hook.py` entry, the slots and page contexts, and the `chemunited`
module that pages import.

## Full override

A project can instead supply its own pre-built dashboard, and the work-server prefers it over the bundled one — no
code changes to `chemunited-workflow` required. Drop a built SPA here:

```text
my_project/
└── customizations/
    └── ui/
        └── dist/
            ├── index.html
            └── assets/
                ├── index-XXXXXXXX.js
                └── index-XXXXXXXX.css
```

`GET /`, `/run-control`, `/protocols`, `/monitoring`, `/devices`, `/logs`, `/export` (and any other one-segment page
URL) serve `customizations/ui/dist/index.html` if it exists for the currently loaded project, otherwise the bundled
dashboard. `GET /assets/{filename}` resolves the same way, checking `customizations/ui/dist/assets/` first.

<div class="info-block">
<strong>💡 Note</strong><br>
Your build must emit <strong>root-absolute</strong> asset URLs (<code>/assets/xyz.js</code>, not
<code>./assets/xyz.js</code>) — this is Vite's default with no custom <code>base</code> set, so pointing any Vite
project's <code>outDir</code> at <code>customizations/ui/dist</code> works with no extra config.
</div>

While `customizations/ui/dist/` exists, it replaces the whole dashboard, so `ui_hook.py` is not applied. The dashboard
favicon always comes from the package.

<div class="info-block">
<strong>💡 Note</strong><br>
The work-server also exposes <code>GET /project-static/&#123;filename&#125;</code>, serving raw files from
<code>&lt;project&gt;/customizations/ui/static/&lt;filename&gt;</code>: a generic file passthrough for data a page
links to.
</div>

## Modifying the bundled default

To change the dashboard every project gets by default, edit the Vue source directly and rebuild — see the
`chemunited-workflow` package's own `docs/html-ui.md` for the `.web-chemunited/` source layout and build steps.

If you need a dashboard that's genuinely independent of the package — own release cycle, no vendored source to touch —
build a separate frontend against the REST/MCP API instead; see [API & MCP Tools](../dashboard/api_and_mcp.md).

## Next steps

See [Working with Backend](backend.md) for the rest of the project file format.
