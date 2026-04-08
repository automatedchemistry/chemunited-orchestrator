# Task — Command Editor Window (skeleton)

## Context

The workflow canvas lets users build processes from blocks. When the user
double-clicks a **command block**, a dialog opens so they can edit the
command parameters. If the user needs more flexibility than the form
provides, they can convert the block to a script — the dialog closes and
the script editor opens with the code pre-filled.

Build the skeleton for both windows.

---

## Files involved

```
src/chemunited/qt/elements/component/widgets/command_editor/
    __init__.py            — public exports
    command.py             — CommandEditorDialog  ← main work here
    script.py              — ScriptEditorDialog   ← main work here
    example.py             — standalone visual test (run this first)
```

take a look at src\chemunited\qt\shared\editor\protocols\image.png to see the expected layout.

Supporting files (read, do not modify unless noted):

```
src/chemunited/qt/elements/component/protocols/models.py
    CommandSignature       — base Pydantic model for all commands
    ComponentProtocol      — registry that holds command classes

src/chemunited/qt/shared/widgets/base_mode_editor/editor_widget.py
    BaseModeEditorWidget   — auto-renders Pydantic model fields as cards

src/chemunited/qt/shared/widgets/base_mode_editor/card_factory.py
    CardFactory            — maps field types to card widgets

src/chemunited/qt/shared/editor/base.py
    EditorBase             — base class for script editors
```

---

## Step 1 — verify the skeleton runs

```bash
python -m chemunited.qt.shared.editor.protocols.example
```

Expected behaviour:

1. `CommandEditorDialog` opens showing two parameter cards (`rate`, `volume`)
   rendered by `BaseModeEditorWidget` from `WithdrawParameter`.
2. Clicking **Save** prints the `CommandSignature` instance to stdout and
   closes the dialog.
3. Clicking **convert to script** opens `_ConfirmConvertDialog`.
4. Confirming the conversion closes `CommandEditorDialog` and opens
   `ScriptEditorDialog` with the pre-filled `def script(...)` source and
   the purple notice banner.
5. Clicking **Save** in `ScriptEditorDialog` prints the source to stdout.

Fix any import errors or crashes before continuing.

---

## Step 2 — hide base fields from the parameter cards

`BaseModeEditorWidget` renders **every** field on the model, including the
base fields inherited from `CommandSignature` (`component`, `command`,
`method`, `description`, `wait_time`, `wait_feedback_status`, `id`).

These should **not** appear as editable cards — they are shown read-only in
the header or handled separately (execution control section).

Pass `field_overrides` to `BaseModeEditorWidget` in `CommandEditorDialog._build_ui`
to hide them:

```python
BASE_FIELDS = set(CommandSignature.model_fields)

overrides = {
    name: {"visible": False, "editable": False}
    for name in BASE_FIELDS
}

self._editor = BaseModeEditorWidget(
    model_class=self._command_class,
    instance=self._instance,
    field_overrides=overrides,
    parent=self,
)
```

After this change only the user-facing parameter fields (e.g. `rate`,
`volume`) should be visible as cards.

---

## Step 3 — add the execution control section

Below the parameter cards, add an **Execution control** section directly
inside `CommandEditorDialog._build_ui` (below the `BaseModeEditorWidget`,
above the footer).

The section contains two controls that map directly to `CommandSignature`
base fields:

| Control | Field | Widget |
|---|---|---|
| Custom wait after (s) | `wait_time: float` | `DoubleSpinBox` or `FloatFieldCard`, visible only when toggled on |
| Wait for device feedback | `wait_feedback_status: bool` | toggle / `SwitchButton` |

Pre-populate both controls from `self._instance` when the dialog opens.

When `_build_script_source` runs, read the values back from these controls
rather than from `self._instance` directly so edits are reflected in the
generated code.

---

## Step 4 — replace the QPlainTextEdit placeholder

In `script_window.py`, the code area is a plain `QPlainTextEdit`:

```python
# TODO: replace QLabel placeholder with a real code editor widget
self._editor = QPlainTextEdit()
```

Replace it with whichever editor component the rest of the project uses
(check the existing Script Editor window for the component name and import
path). The replacement must expose at least:

- `setPlainText(str)` — or equivalent — to set initial content
- `toPlainText() -> str` — or equivalent — to read current content

`ScriptEditorDialog.get_source()` and `_on_save()` both call
`self._editor.toPlainText()`, so update those calls if the API differs.

---

## Step 5 — wire the assistant sidebar buttons

In `ScriptEditorDialog._build_sidebar`, four buttons have a `# TODO`:

```python
# TODO: connect each button to the appropriate insertion helper
```

Each button should insert a code snippet at the current cursor position in
the editor:

| Button | Action |
|---|---|
| **add command** | Open the existing "Add new command" dialog (see screenshot in task). On confirm, insert the generated `platform[...].put(...)` call at cursor. |
| **pathway** | Open the PathWay Selection helper. On confirm, insert the pathway command at cursor. |
| **process param** | Show a list of `ProcessParameters` fields. On select, insert `process_parameters.<name>` at cursor. |
| **main param** | Show a list of `MainParameters` fields. On select, insert `parameters.<name>` at cursor. |

The **black format** button at the bottom should run `black` on the full
source and reload the editor with the formatted result.

---

## Step 6 — integrate into the canvas double-click handler

Find where the workflow canvas handles `mouseDoubleClickEvent` (or
`itemDoubleClicked`) for command blocks. Replace the existing handling (if
any) with:

```python
from chemunited.qt.elements.component.widgets.command_editor import (
    CommandEditorDialog,
    ScriptEditorDialog,
)

def _on_block_double_clicked(self, block) -> None:
    if block.block_type != "command":
        return

    protocol = block.protocol          # ComponentProtocol instance
    cmd_class = protocol.commands[block.command_key]
    instance = block.command_instance  # CommandSignature | None

    dlg = CommandEditorDialog(
        command_class=cmd_class,
        instance=instance,
        parent=self,
    )

    def _on_convert(source: str) -> None:
        script_dlg = ScriptEditorDialog(
            block_name=block.name,
            source=source,
            converted_from_command=True,
            parent=self,
        )
        script_dlg.saved.connect(lambda src: block.set_script_source(src))
        script_dlg.exec_()

    dlg.convert_to_script.connect(_on_convert)
    dlg.saved.connect(lambda inst: block.set_command_instance(inst))
    dlg.exec_()
```

Adjust attribute names (`block.protocol`, `block.command_key`, etc.) to
match the actual block object in your canvas.

---

## Acceptance criteria

- [ ] `example.py` runs without errors.
- [ ] Only user-facing parameter fields appear as editable cards (base
      fields are hidden).
- [ ] Execution control section shows current `wait_time` and
      `wait_feedback_status` values and round-trips them correctly through
      `_build_script_source`.
- [ ] Confirming "convert to script" closes `CommandEditorDialog` and opens
      `ScriptEditorDialog` with the correct pre-filled source and the purple
      notice banner.
- [ ] The code editor in `ScriptEditorDialog` uses the project's standard
      editor component, not `QPlainTextEdit`.
- [ ] All four assistant sidebar buttons are connected and insert the
      correct snippet at cursor.
- [ ] Double-clicking a command block on the canvas opens
      `CommandEditorDialog` correctly.

---

## Notes

- Neither dialog should know about the other. All coordination happens
  through signals in the caller (canvas or `example.py`).
- `_build_script_source` in `CommandEditorDialog` already produces a valid
  `def script(...)` wrapper. Do not duplicate this logic in the canvas.
- The `converted_from_command=True` flag on `ScriptEditorDialog` only
  controls whether the purple notice banner is shown — it has no effect on
  functionality.
