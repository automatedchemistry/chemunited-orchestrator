# Dashboard customization

The files here change this project's dashboard. Nothing is built: the server
reads `ui_hook.py`, and the browser compiles the `.vue` files when it loads them.
Edit a file and reload the page.

- `ui_hook.py`: brand, nav, pages, buttons that call your Python routes, widgets.
- `pages/`: custom pages (`.vue`). `HelloPage.vue` is an example.
- `theme.css`: colours, once `ui_hook.py` names it.
- `types/`, `tsconfig.json`: let an editor such as VS Code (with the Vue
  extension) check your `.vue` files as you type. `chemunited-workflow ui init`
  refreshes `types/`.
- `.oxlintrc.json`: lint settings for `chemunited-workflow ui check`.

Check everything with:

```bash
pip install "chemunited-workflow[ui-lint]"
chemunited-workflow ui check <project_dir>
```

The dashboard's **Customizations** page compiles every file and lists any problems.
Guide: chemunited-workflow's `docs/html-ui.md#runtime-customizations`.
