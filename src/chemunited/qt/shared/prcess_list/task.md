# Task: Implement ProcessList Widget (PyQt + qfluentwidgets)

## Context

This widget is part of **ChemUnited**, a Python desktop application for chemistry automation workflows built with PyQt and `qfluentwidgets`. The goal is a reusable, extensible process list widget split across three files.

---

## Mental Model

```
user interaction → ProcessItem emits signal → ProcessList reacts
```

- **`ProcessItem`** is concrete and never subclassed. It is passive — it emits signals when things happen and knows nothing about consequences. All items are identical: same options, same behavior.
- **`ProcessList`** is the foundation class, designed to be subclassed. It owns all logic, connects to item signals, and implements all callables. It is configured once in the subclass `__init__` and that configuration applies to every item — present and future — automatically.
- **`ProcessWidget`** is a concrete visual shell. It receives a `ProcessList` instance from outside and wraps it with a separator and a bottom button bar. It has no opinion about the list it contains.

---

## File Structure

```
item.py
list.py
widget.py
```

---

## Dependencies

- PyQt6 (or PyQt5 — match what is already used in the project)
- `qfluentwidgets` — use `RoundMenu`, `Action`, `LineEdit`, `ToolButton`, `PushButton`, `FluentIcon`, `ListWidget`
- `loguru` for warnings

---

## File 1: `item.py` — `ProcessItem`

### Description

A passive, uniform `QWidget` representing one row in the list. Emits signals when things happen. Never subclassed. All instances are identical in structure and behavior — they only differ in their `name`.

### Internal State

- `_name: str`
- `_enable_rename: bool = False`
- `_editing: bool = False`
- `_menu: RoundMenu | None = None` — instantiated on first `add_option` call
- `_menu_button: ToolButton` — hidden until the first option is added

### Layout

A `QStackedWidget` with two pages:

- **Page 0 — display mode:** horizontal layout with:
  - Status icon placeholder: a `QLabel` with fixed small size, empty for now
  - Name label: fluent `BodyLabel`
  - Menu button: `ToolButton` with `FluentIcon.MORE`, hidden by default

- **Page 1 — edit mode:** a single fluent `LineEdit` pre-filled with the current name

### `name` Property

```python
@property
def name(self) -> str:
    return self._name
```

### Signals

```python
option_triggered = pyqtSignal(str, str)   # (option_name, process_name)
rename_requested = pyqtSignal(str, str)   # (current_name, proposed_name)
edit_started = pyqtSignal(str)            # (process_name) — for exclusivity management
```

### Public Methods

#### `add_option(name: str, icon, tip: str)`

- Instantiates `_menu` on first call
- Adds an `Action` to the menu with the given name, icon, and tip
- The action's triggered callback emits `option_triggered(name, self._name)`
- Makes `_menu_button` visible
- Connects `_menu_button` to show the menu at the correct screen position

> **Note:** No callable is passed here. The item only emits `option_triggered`. The list owns all logic.

#### `enable_rename()`

- Sets `_enable_rename = True`
- Calls `add_option("Rename", <icon>, "Rename this process")`
- Internally connects the "Rename" `option_triggered` to `_enter_edit_mode()` — this is the one exception where the item connects its own signal to itself, because edit mode is purely a visual/internal concern

#### `set_name(name: str)`

- Updates `_name`
- Updates the display label text
- Emits no signal

#### `set_status(status)`

- No-op placeholder — accepts any argument, ready for a future enum

### Private Methods

#### `_enter_edit_mode()`

- If `_editing` is `True`, return immediately
- Set `_editing = True`
- Emit `edit_started(self._name)`
- Pre-fill `LineEdit` with `self._name`, select all text, set focus
- Switch `QStackedWidget` to page 1

#### `_exit_edit_mode(confirm: bool)`

- If `_editing` is `False`, return immediately (idempotent guard)
- Set `_editing = False`
- Switch `QStackedWidget` to page 0
- If `confirm=True`:
  - Read and strip text from `LineEdit`
  - If empty or equal to `self._name`: silent cancel, do nothing
  - Otherwise: emit `rename_requested(self._name, proposed_name)`

### Key Event Handling on `LineEdit`

- `returnPressed` → `_exit_edit_mode(confirm=True)`
- `Escape` key (via event filter or `keyPressEvent`) → `_exit_edit_mode(confirm=False)`
- Focus loss (`focusOutEvent`) → `_exit_edit_mode(confirm=True)`

> **Important:** The `_editing` guard in `_exit_edit_mode` makes all exit paths idempotent — no double-trigger is possible.

---

## File 2: `list.py` — `ProcessList`

### Description

Foundation class designed to be subclassed. Manages all `ProcessItem` widgets. Owns the external dict reference and keeps it synchronized. All logic and callables live here or in subclasses. Configuration methods apply uniformly to every item — past and future.

### Constructor

```python
def __init__(self, data: dict, parent=None)
```

- Store the external dict reference (do not copy)
- Create a fluent `ListWidget` with `setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)`
- Initialize:
  - `_option_specs: list[tuple[str, icon, str]] = []` — registered option specs
  - `_rename_enabled: bool = False`
  - `_editing_item: ProcessItem | None = None`
  - `_dispatch: dict[str, callable] = {}` — maps option_name → handler method

### Signals

```python
selection_changed = pyqtSignal(str)       # name of selected item, or "" if deselected
process_renamed = pyqtSignal(str, str)    # (old_name, new_name)
```

Connect `ListWidget.currentItemChanged` → internal slot → emit `selection_changed(name or "")`.

### Configuration Methods

Called in the subclass `__init__` to shape behavior. Apply to all existing items and all future items.

#### `set_items_renameable(enabled: bool)`

- Store `_rename_enabled = enabled`
- If `enabled=True`: call `item.enable_rename()` on all existing items

#### `add_items_option(name: str, icon, tip: str)`

- Append `(name, icon, tip)` to `_option_specs`
- Call `item.add_option(name, icon, tip)` on all existing items

### Item Management Methods

#### `add_process(name: str)`

- If `name` already exists in `data`: `logger.warning(...)` and return
- Create `ProcessItem(name)`
- If `_rename_enabled`: call `item.enable_rename()`
- Apply all `_option_specs`: call `item.add_option(...)` for each
- Connect signals:
  - `item.edit_started` → `_on_edit_started`
  - `item.rename_requested` → `_on_rename_requested`
  - `item.option_triggered` → `_on_option_triggered`
- Create a `QListWidgetItem`, set size hint, add to `ListWidget`, embed widget via `setItemWidget`
- Add `name` to `data` with value `None`

#### `remove_process(name: str)`

- If `name` not in `data`: `logger.warning(...)` and return
- Find the `QListWidgetItem` whose widget's `name == name`, remove it from `ListWidget`
- Delete `data[name]`

#### `rename_process(old_name: str, new_name: str)`

- If `new_name` already in `data`: `logger.warning(...)` and return
- If `old_name` not in `data`: `logger.warning(...)` and return
- Find the item with `name == old_name`
- Call `item.set_name(new_name)`
- `data[new_name] = data.pop(old_name)`
- Emit `process_renamed(old_name, new_name)`

### Access / Helper Methods

#### `selected_name() -> str | None`

- Return `itemWidget(currentItem()).name` or `None` if nothing selected

#### `names() -> list[str]`

- Iterate `ListWidget` rows top to bottom
- Return `[itemWidget(item).name for item in rows]`
- Reflects visual order — dict order is irrelevant

#### `sync()`

- `data_keys = set(data.keys())`
- `list_names = set(self.names())`
- For names in `list_names - data_keys`: remove the widget row from `ListWidget` directly (key is already gone from dict — do **not** call `remove_process`, just remove the row)
- For names in `data_keys - list_names`: call `add_process(name)`, then restore the original dict value: `data[name] = original_value` (capture it before calling `add_process`)
- Items present in both are left untouched

### Internal Signal Handlers

#### `_on_edit_started(process_name: str)`

- If `_editing_item` is not `None` and is a different item: call `_editing_item._exit_edit_mode(confirm=False)`
- Find the item by name and set `_editing_item` to it

#### `_on_rename_requested(current_name: str, proposed_name: str)`

- Call `rename_process(current_name, proposed_name)`
- Set `_editing_item = None`

#### `_on_option_triggered(option_name: str, process_name: str)`

- Look up `option_name` in `_dispatch`
- If not found: `logger.warning(...)` and return
- Call `_dispatch[option_name](process_name)`

### Subclassing Pattern

```python
class MyProcessList(ProcessList):
    def __init__(self, data: dict, parent=None):
        super().__init__(data, parent)

        # Configure all items uniformly
        self.set_items_renameable(True)
        self.add_items_option("Duplicate", FluentIcon.COPY, "Duplicate this process")
        self.add_items_option("Remove", FluentIcon.DELETE, "Remove this process")

        # Register handlers in dispatch table
        self._dispatch["Duplicate"] = self._on_duplicate
        self._dispatch["Remove"] = self._on_remove

    def _on_duplicate(self, name: str):
        self.add_process(f"{name}_copy")

    def _on_remove(self, name: str):
        self.remove_process(name)
```

---

## File 3: `widget.py` — `ProcessWidget`

### Description

A concrete `QFrame` visual shell. Receives a `ProcessList` instance from outside. Wraps it with a horizontal separator and a bottom button bar. Has no opinion about the list it contains.

### Constructor

```python
def __init__(self, process_list: ProcessList, parent=None)
```

- Store `_list = process_list`
- Build vertical layout:
  - `_list` (stretch = 1)
  - Horizontal separator (`HorizontalSeparator` from qfluentwidgets, or a styled `QFrame`)
  - Bottom button row: `QHBoxLayout`, left-aligned, with a `QSpacerItem` stretch at the end
- Forward signals:
  - `_list.selection_changed` → `self.selection_changed`
  - `_list.process_renamed` → `self.process_renamed`

### Signals

```python
selection_changed = pyqtSignal(str)
process_renamed = pyqtSignal(str, str)
```

### Methods

#### `add_bottom_button(name: str, icon, tip: str, callable) -> PushButton`

- Create a fluent `PushButton` with icon and name as text
- Set tooltip to `tip`
- Connect `clicked` to `callable`
- Insert **before** the stretch spacer in the bottom `QHBoxLayout`
- Return the button so the caller can `setEnabled(False)` etc.

#### `add_separator()`

- Insert a vertical `QFrame` line (`QFrame.Shape.VLine`) before the stretch spacer
- Style it to match the fluent theme

---

## Self-Contained Test

At the bottom of `widget.py`, add:

```python
if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication
    from qfluentwidgets import FluentIcon

    class DemoList(ProcessList):
        def __init__(self, data, parent=None):
            super().__init__(data, parent)
            self.set_items_renameable(True)
            self.add_items_option("Remove", FluentIcon.DELETE, "Remove this process")
            self._dispatch["Remove"] = self._on_remove

        def _on_remove(self, name: str):
            self.remove_process(name)

    app = QApplication(sys.argv)

    data = {"Calibration": None, "Clean": None, "React": None}
    lst = DemoList(data)
    widget = ProcessWidget(lst)

    widget.add_bottom_button(
        "Add", FluentIcon.ADD, "Add a new process",
        lambda: lst.add_process(f"process_{len(data)}")
    )
    widget.add_separator()
    widget.add_bottom_button(
        "Remove", FluentIcon.DELETE, "Remove selected process",
        lambda: lst.remove_process(lst.selected_name()) if lst.selected_name() else None
    )

    widget.selection_changed.connect(lambda name: print(f"Selected: {name!r}"))
    widget.process_renamed.connect(lambda old, new: print(f"Renamed: {old!r} -> {new!r}"))

    widget.resize(320, 480)
    widget.show()
    sys.exit(app.exec())
```

---

## Style and Quality Rules

- Type hints throughout
- `from loguru import logger` at the top of each file
- No `print()` in production code — only in the test block
- Cross-imports: `process_list.py` imports from `process_item.py`; `process_widget.py` imports from `process_list.py`
- All `qfluentwidgets` imports from correct submodules
- PEP8, 4-space indentation
