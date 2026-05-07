# Parameters Editor

Card-based editor for Pydantic parameter models used in the Qt UI.

This package provides a focused editor for one model class inside a Python file.
It loads the class, builds one card per supported field, and writes the class
back to disk only after a valid user change.

## Current behavior

- Single-view editor centered on the parameter card list
- No embedded script editor
- Live writes only for valid user changes
- No writes during startup or card population
- Existing code outside the edited class is preserved
- Non-field members inside the class are preserved when the class is rewritten

## Main pieces

- `main.py`
  - Builds `MainParametersEditor`
  - Loads the target model class from file
  - Maps `FieldInfo` into the corresponding `*BuildMode`
  - Splices the regenerated class definition back into the original file

- `list.py`
  - Provides `ParameterListWidget`
  - Hosts all `VariableCard` instances inside a Fluent `SmoothScrollArea`
  - Suppresses writes during bulk loading with `suspend_writes()`
  - Flushes changes only when the full card state is valid

- `cards.py`
  - Provides `VariableCard`
  - Renders one editable card for one field definition
  - Shows validation errors inline at the bottom of the card
  - Emits a lightweight `changed` signal when the card state changes

- `drag_list.py`
  - Provides `ParameterDragableList`
  - Read-only `QListWidget`-based view of Pydantic model field names
  - Items are draggable as plain text (`text/plain` MIME), suitable for
    dropping into script editors or code cells
  - No editing, no validation, no file writes

- `example.py`
  - Example Pydantic model used for manual testing and iteration

## Supported field types

- `str`
- `int`
- `float`
- `bool`
- `list`
- `str` with `json_schema_extra["Options"]` for choice fields
- `Annotated[ChemUnitQuantity, ChemQuantityValidator(...)]` for quantity fields

## Data flow

1. `MainParametersEditor` loads the target class from a file.
2. Each Pydantic field is converted into a matching build-mode object.
3. `ParameterListWidget` creates one `VariableCard` per field.
4. When the user edits a card, the card validates its current state.
5. If all cards are valid, the list renders the class source.
6. `main.py` writes the updated class back into the original file.

## Notes for contributors

- Keep this editor card-first and lightweight.
- Prefer updating behavior in the build-mode models and card conversion logic
  before adding special-case UI branches.
- Validation errors should stay local to the card when possible.
- File writes should remain user-driven and valid-only.

## Quick usage

Typical entrypoint:

```python
from pathlib import Path

from chemunited.qt.shared.editor.parameters.main import MainParametersEditor

window = MainParametersEditor(
    path=Path("path/to/parameters.py"),
    class_name="ProcessParameters",
)
window.show()
```

Draggable field-name list (read-only, drag into a script editor):

```python
from pathlib import Path

from chemunited.qt.shared.editor.parameters.drag_list import ParameterDragableList

widget = ParameterDragableList(
    path=Path("path/to/parameters.py"),
    class_name="ProcessParameters",
)
widget.show()
```
