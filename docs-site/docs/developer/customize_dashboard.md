# Customize dashboard

The browser [dashboard](../dashboard/overview.md) (all six pages — Dashboard, Run Control, Protocols, Monitoring,
Devices, Logs) is a single Vue single-page app served by the work-server (`chemunited-workflow`). Every route serves
the same `index.html`; Vue Router handles navigation between pages client-side.

## Per-project override

A project can supply its own pre-built dashboard, and the work-server prefers it over the bundled one automatically
— no code changes to `chemunited-workflow` required. Drop a built SPA here:

```text
my_project/
└── ui/
    ├── dist/
    │   ├── index.html
    │   └── assets/
    │       ├── index-XXXXXXXX.js
    │       └── index-XXXXXXXX.css
    └── static/          # unrelated: served at /project-static/{filename}, see note below
```

`GET /`, `/run-control`, `/protocols`, `/monitoring`, `/devices`, and `/logs` serve `ui/dist/index.html` if it
exists for the currently loaded project, otherwise the bundled dashboard. `GET /assets/{filename}` resolves the same
way, checking `ui/dist/assets/` first.

<div class="info-block">
<strong>💡 Note</strong><br>
Your build must emit <strong>root-absolute</strong> asset URLs (<code>/assets/xyz.js</code>, not
<code>./assets/xyz.js</code>) — this is Vite's default with no custom <code>base</code> set, so pointing any Vite
project's <code>outDir</code> at <code>ui/dist</code> works with no extra config. Other bundlers work too as long as
they emit the same root-absolute convention.
</div>

Two limitations to be aware of:

* The dashboard favicon always comes from the package — it isn't overridable.
* Only the six page paths above are server-routed. A custom SPA should reuse those route names for anything that
  needs to survive a hard refresh or direct link; client-side navigation within your app works for any other route.

<div class="info-block">
<strong>💡 Note</strong><br>
The work-server also exposes <code>GET /project-static/&#123;filename&#125;</code>, serving raw files from
<code>&lt;project&gt;/ui/static/&lt;filename&gt;</code>. This is unrelated to the dashboard override above — a
generic file passthrough only, reachable only by linking to its URL directly from somewhere else.
</div>

## Modifying the bundled default

To change the dashboard every project gets by default (i.e. when it doesn't supply its own `ui/dist/` override),
edit the Vue source directly and rebuild — see the `chemunited-workflow` package's own `docs/html-ui.md` for the
`.web-chemunited/` source layout and build steps.

If you need a dashboard that's genuinely independent of the package — own branding, own release cycle, no vendored
source to touch — build a separate frontend against the REST/MCP API instead; see
[API & MCP Tools](../dashboard/api_and_mcp.md).

## Next steps

See [Working with Backend](backend.md) for the rest of the project file format.
