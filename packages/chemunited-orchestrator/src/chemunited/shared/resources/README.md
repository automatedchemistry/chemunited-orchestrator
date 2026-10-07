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

## Component palette icons

Component figures live in `chemunited-core`'s `figure_registry`
(`chemunited_core.figure_registry`), which is the single source of truth for
component artwork. **Do not draw a new figure here.** If you're adding a new
device type, or a new device that can reuse an existing figure, register it in
`chemunited_core.figure_registry` instead.

The `components/` folder holds the tree-palette icon
([tree_add.py](../../draw/tree_add.py)) for every built-in component. These
icons are *generated*, not hand-drawn: each one is the composed
`GraphComponent` (all figure layers, rotary-valve ports, connection points)
exported with `GraphComponent.export_svg()`. That is why many components that
share one core figure (the rotary valves, `Source`/`Sink`, the `Power`
devices, `SyringePump`'s barrel + plunger) still get distinct, accurate icons.

`tree_add.py._component_icon` looks an icon up by **exact component name**
(`:/components_icons/components/<Name>.svg`) and falls back to the raw core
figure when there is none (e.g. project-local custom components).

The icons are a snapshot, so **regenerate them whenever figures change or a
component is added**. From `packages/chemunited-orchestrator`:

```powershell
python src\chemunited\elements\component\__render_components.py --icons src\chemunited\shared\resources\components
```

Then add any new `<file>components/<Name>.svg</file>` entries to the
`/components_icons` section of `resources_rc.qrc` and rebuild
`resources_rc.py` (see below). The analytics instruments draw a random demo
spectrum, so their SVGs differ slightly on every export — that is expected.

Resulting runtime path, e.g.:

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

Run this from `packages/chemunited-orchestrator`:

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
