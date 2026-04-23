# Process List Shared Widgets

## Overview

This package contains the shared Qt widgets used to display and interact with process lists in the ChemUnited UI.

The original `task.md` in this folder described a target design. That work has since been implemented, and the code here now provides the reusable foundation used by the protocol process list. This README documents the implementation that already exists today.

Files in this package:

```text
item.py
list.py
widget.py
__init__.py
```

The import path is currently:

```python
chemunited.qt.shared.prcess_list
```

The folder name intentionally matches the current codebase, including the existing `prcess_list` spelling.

## Current Design

The shared layer is built around three responsibilities:

- `ProcessItem` is the row widget and emits UI-level signals.
- `ProcessList` owns list rendering, shared option wiring, selection handling, and edit exclusivity.
- `ProcessWidget` wraps a `ProcessList` with shared framing and bottom actions.

The current data flow is:

```text
user action -> ProcessItem signal -> ProcessList dispatch or forwarding -> feature-specific owner mutates external state -> ProcessList.sync()
```

This is slightly different from the earlier task plan. The shared list does not currently own the full add/remove/rename mutation lifecycle itself. Instead, it is designed to stay in sync with an external dictionary owned by a higher-level feature, and subclasses decide what to do with rename/remove/duplicate intentions.

## `item.py`

`item.py` implements the passive row widget, `ProcessItem`.

Implemented behavior:

- Stores the process name internally and exposes it through `name`
- Renders two stacked modes with `QStackedWidget`
- Display mode contains:
  - a small `_StatusCircle` placeholder
  - a `BodyLabel` with the process name
  - a `ToolButton` with `FluentIcon.MORE`
- Edit mode contains a custom `_EditLineEdit`
- Emits:
  - `option_triggered(str, str)`
  - `rename_requested(str, str)`
  - `edit_started(str)`
- Lazily creates a `RoundMenu` when the first option is added
- Supports inline rename through `enable_rename()`
- Updates the visible label through `set_name()`
- Keeps a placeholder `set_status()` hook for future status UI

Inline rename is already implemented:

- entering edit mode selects the full current name
- Enter confirms
- Escape cancels
- focus loss confirms
- `_editing` guards the transitions so duplicate exits are avoided

## `list.py`

`list.py` implements `ProcessList`, the shared base widget around a fluent `ListWidget`.

Implemented behavior:

- stores a reference to the external `data` dictionary
- creates and owns the `ListWidget`
- enables internal drag/drop on the view
- tracks:
  - registered option specs
  - whether rename is enabled
  - the item currently being edited
  - a dispatch table for option handlers
- emits:
  - `selection_changed(str)`
  - `process_renamed(str, str)`
- forwards list selection changes as process names
- ensures only one item is in inline edit mode at a time
- routes item menu actions through `_dispatch`
- applies rename support and menu options to both existing and newly created rows
- exposes:
  - `selected_name()`
  - `names()`
  - `sync()`

`sync()` is the main reconciliation mechanism in the current design. It compares the current widget rows with the external dictionary keys, removes rows that no longer exist in the data source, and creates rows for new entries.

### Important difference from the old plan

The original task document described `add_process()`, `remove_process()`, and `rename_process()` as base-class responsibilities. The current implementation does not provide those shared CRUD methods in `ProcessList`.

Instead:

- higher-level code owns the source-of-truth dictionary
- subclasses or orchestrator code decide what rename/remove/duplicate mean
- the list is refreshed afterward through `sync()`

That is the model used by the current application code.

## `widget.py`

`widget.py` implements `ProcessWidget`, the shared visual shell around any `ProcessList`.

Implemented behavior:

- wraps the provided `ProcessList` inside a `QFrame`
- adds a horizontal separator below the list
- forwards:
  - `selection_changed`
  - `process_renamed`
- provides `add_bottom_button()` to register bottom action buttons
- provides `add_separator()` to insert a separator widget between bottom actions
- provides `sync_list()` as a convenience wrapper around the underlying list `sync()`

This class stays intentionally generic and does not know anything about protocols, workflows, or orchestrator rules.

## Current Consumer

The main consumer of this shared package is:

```python
chemunited.qt.protocols.process_list
```

That module builds on the shared widgets with:

- `ProtocolsList(ProcessList)`
- `ProtocolsWidget(ProcessWidget)`

Current protocol-specific behavior:

- enables inline rename on every item
- adds `Duplicate` and `Remove` menu actions
- uses `_dispatch` for shared menu routing
- emits higher-level intention signals:
  - `rename_requested`
  - `remove_requested`
  - `duplicate_requested`
- lets orchestrator code mutate the actual `protocols` dictionary
- calls `sync()` after those mutations so the list re-renders from source state

This means the shared package is already in active use as a reusable UI foundation, while business rules stay in the protocol/orchestrator layer.

## Orchestrator Integration Pattern

The owning flow today lives in `chemunited.qt.orchestrator.protocols`.

That layer documents and uses this mutation pattern:

1. Validate the requested change.
2. Write to the source-of-truth `protocols` dictionary.
3. Update the workflows view.
4. Call `protocols_widget.sync_list()` so the shared list reconciles itself from the dict.

That pattern matches the current shared widget implementation much better than the older plan document did.

## Notes About Scope

What is already implemented well:

- reusable passive row widget
- inline rename UI
- shared menu option registration
- centralized dispatch in the list base class
- selection forwarding
- edit exclusivity
- external-dictionary synchronization
- reusable shell widget for bottom actions
- protocol-specific reuse through subclassing

What is not implemented as originally planned:

- base-class `add_process()`
- base-class `remove_process()`
- base-class `rename_process()`
- a fully self-contained CRUD list component that mutates its own backing data

So the package should be understood as a shared render-and-intent layer, not as a full standalone process manager.

## Demo Note

`widget.py` still contains a local `__main__` demo block. That block is useful as a quick manual scaffold, but it reflects the older CRUD-style assumptions more than the current sync-driven architecture. The production integration path is the protocol/orchestrator flow described above.
