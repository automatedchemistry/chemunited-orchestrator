# Adding new resources

This project stores Qt resources in:

- `src/chemunited/shared/resources/resources_rc.qrc`
- Generated Python module: `src/chemunited/shared/resources/resources_rc.py`

When you add a new figure, icon, or stylesheet, the usual workflow is:

1. Put the file in the correct folder under `src/chemunited/shared/resources/`.
2. Add the file to `resources_rc.qrc`.
3. Rebuild `resources_rc.py` with `pyrcc5`.
4. Use the generated Qt resource path in the code.

## Folder layout

- `icons/`: small UI icons, mostly `.svg`
- `components/`: component-specific icon *overrides* (see below), `.svg`
- `qss/`: stylesheets

## How the Qt resource paths are built

The final runtime path is:

```text
:/<prefix>/<relative path written in the .qrc file>
```

Examples from this project:

- Prefix `/styles` + file `qss/dark/main_window.qss`
  becomes `:/styles/qss/dark/main_window.qss`
- Prefix `/icons` + file `icons/air.svg`
  becomes `:/icons/icons/air.svg`
- Prefix `/components_icons` + file `components/Gantry3D.svg`
  becomes `:/components_icons/components/Gantry3D.svg`

## Adding a new icon

Put the new icon file in:

```text
src/chemunited/shared/resources/icons/
```

Then add it to the `/icons` section in `resources_rc.qrc`, for example:

```xml
<qresource prefix="/icons">
    <file>icons/new_icon.svg</file>
</qresource>
```

### Naming convention for themed icons

`src/chemunited/shared/icon.py` looks for themed icons in this order:

1. `:/icons/icons/<name>_white.svg` or `:/icons/icons/<name>_black.svg`
2. If those do not exist, `:/icons/icons/<name>.svg`

So you have two valid patterns:

- Single icon for both themes:

```text
new_icon.svg
```

- One icon per theme:

```text
new_icon_black.svg
new_icon_white.svg
```

If you want to use the icon through `OrchestratorIcon`, also add an enum entry in:

```text
src/chemunited/shared/icon.py
```

Example:

```python
NEW_ICON = "new_icon"
```

## Adding a new component icon override

Component figures live in `chemunited-core`'s `figure_registry`
(`chemunited_core.figure_registry`), which is the single source of truth for
component artwork — the tree palette
([tree_add.py](../../draw/tree_add.py)) and the canvas rendering
(`graph_item.py`) both resolve a component's icon from there by default via
`COMPONENTS[name].figure_base` (or `name` itself) and `get_figure_path(...)`.

**Do not add a new figure here.** If you're adding a new device type, or a
new device that can reuse an existing figure, register it in
`chemunited_core.figure_registry` instead.

This local `components/` folder exists only for the rare case where the tree
palette needs a *different icon than the shared figure* for one specific
component — e.g. `Gantry3D` has its own icon here even though it shares the
`Gantry` figure with `Gantry1D` in core. To add such an override:

1. Put the SVG in `src/chemunited/shared/resources/components/`, named
   **exactly** after the component's `chemunited_core.figure_registry.COMPONENTS`
   key (e.g. `Gantry3D.svg`) — `tree_add.py._component_icon` only looks up an
   override by exact component-name match.
2. Add it to the `/components_icons` section in `resources_rc.qrc`.
3. Rebuild `resources_rc.py` with `pyrcc5` (see below).

Example:

```xml
<qresource prefix="/components_icons">
    <file>components/Gantry3D.svg</file>
</qresource>
```

Resulting runtime path:

```text
:/components_icons/components/Gantry3D.svg
```

## Adding a new stylesheet resource

Put the file in:

```text
src/chemunited/shared/resources/qss/
```

Then register it in the `/styles` section of `resources_rc.qrc`.

Example:

```xml
<qresource prefix="/styles">
    <file>qss/dark/my_widget.qss</file>
    <file>qss/light/my_widget.qss</file>
</qresource>
```

Resulting runtime paths:

```text
:/styles/qss/dark/my_widget.qss
:/styles/qss/light/my_widget.qss
```

## Rebuild the generated resource module

Run this from the repository root:

```powershell
pyrcc5 src\chemunited\shared\resources\resources_rc.qrc -o src\chemunited\shared\resources\resources_rc.py
```

## Important pitfall

Do not put XML comments inside `resources_rc.qrc`.

In this environment, `pyrcc5` can fail with:

```text
No resources in resource description.
```

even when the file entries are correct. If that happens, first check that `resources_rc.qrc` does not contain comments such as:

```xml
<!-- example comment -->
```

## Quick checklist

- File copied into the correct folder
- File added to `resources_rc.qrc`
- Naming follows the existing convention
- `resources_rc.py` regenerated with `pyrcc5`
- Code uses the final Qt resource path, not a filesystem path
