# Dashboard customization example

This folder customizes the bundled dashboard for this project, with no build
step: the dashboard reads [`ui_hook.py`](ui_hook.py) at start-up and compiles the
`.vue` files in the browser. Nothing here needs Node or npm. The full guide is
[`docs/html-ui.md`](../../../../docs/html-ui.md#runtime-customizations).

## Try it

```bash
chemunited-workflow serve examples/custom_project
```

Open `http://127.0.0.1:3116/`. Compared with a project without this folder you get:

- **Reactor** in the nav, after Monitoring: [`pages/ReactorPage.vue`](pages/ReactorPage.vue),
  which reuses [`components/StatTile.vue`](components/StatTile.vue) and calls the
  `residence_time_min` route from `customizations/routers/router_hook.py`.
- **History** in the nav, after Logs: an HTML page that the `protocol_history()`
  function in `ui_hook.py` renders in Python.
- On the **Dashboard**: a "Residence time" button with two number fields, drawn
  from that route's type hints, and [`widgets/RunCard.vue`](widgets/RunCard.vue) in
  the `dashboard.cards` slot.
- On **Export**: a "Summarize" button that sends the selected runs to the
  `summarize_runs` route.
- **Customizations** in the nav: compiles every file and lists any problems.

Edit any file and reload the page to see the change. To rebrand and recolour
the dashboard, uncomment the `brand=` and `theme_css=` lines in `ui_hook.py`.

## Layout

```text
customizations/ui/
├── ui_hook.py              DASHBOARD = Dashboard(...): pages, actions, widgets
├── theme.css               colour tokens, applied when ui_hook.py names it
├── pages/ReactorPage.vue   a custom page
├── components/StatTile.vue a part shared by pages
├── widgets/RunCard.vue     a widget for a slot on a built-in page
└── assets/flask.svg        the Reactor page's nav icon
```

A project can instead replace the whole dashboard with its own prebuilt app in
`customizations/ui/dist/`; that needs a build tool (see
[`docs/html-ui.md`](../../../../docs/html-ui.md#per-project-override)).
