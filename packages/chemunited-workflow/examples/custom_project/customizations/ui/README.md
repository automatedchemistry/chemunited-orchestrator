# Custom dashboard example

This is a working example of the per-project dashboard override described in
[`docs/html-ui.md`](../../../../docs/html-ui.md#per-project-override). It's a
plain HTML/CSS/JS single-page app — no npm, no build step — that talks to the
same REST API the bundled Vue dashboard uses.

It's read-only: it only issues `GET` requests (plus `/components/ping`, which
doesn't mutate anything), so it's safe to click around without starting a run
or changing project state.

## Try it

```bash
chemunited-workflow serve examples/custom_project
```

Open `http://127.0.0.1:3116/`. You should see the amber "Flow Synthesis
Reactor" theme instead of the bundled blue Vue dashboard — confirming
`{project_dir}/customizations/ui/dist/index.html` is being served in place
of the package default. All six nav tabs (`/run-control`, `/protocols`,
`/monitoring`, `/devices`, `/logs`) do a real navigation to that same
overridden page; the JS in `assets/dashboard.js` reads `location.pathname`
to decide which section to show, and its own `<link>`/`<script>` tags are
served via `{project_dir}/customizations/ui/dist/assets/`.

To compare against the default, point the server at a project with no
`customizations/ui/dist/` directory (or just delete this folder) and
reload — you'll get the bundled Vue dashboard back automatically.

## Layout

```
customizations/ui/dist/
├── index.html          # one shell containing all 6 tab sections
└── assets/
    ├── dashboard.css
    └── dashboard.js     # fetch() calls against /project/, /processes/, /protocols/, /logs/, /components/, /monitoring/, /run/
```
