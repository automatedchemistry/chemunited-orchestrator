"""
main.py
=======
MainParametersEditor
--------------------
Two-tab window:

  Tab 0  "Parameters List"  →  ParameterListWidget  (card editor)
  Tab 1  "Script Editor"    →  Editor (QsciScintilla, shows the live file)

Usage
-----
    win = MainParametersEditor(
        path=Path("path/to/parameters.py"),
        class_name="ProcessParameters",
    )
    win.show()

On startup, the window:
  1. Loads the class ``class_name`` from ``path`` using importlib.
  2. Walks ``model_fields`` and maps every field to the correct ``*BuildMode``.
  3. Builds one card per field — no manual pre-population needed.

On every card edit:
  - The card regenerates its ``Field(...)`` snippet.
  - ``ParameterListWidget`` assembles the full class source.
  - The source is spliced back into ``path`` atomically (imports and any
    code above/below the class are preserved verbatim).
  - The Script Editor tab is updated to reflect the new content.
"""

from __future__ import annotations

import ast
import copy
from functools import partial
from pathlib import Path
from typing import Any, Annotated, get_args, get_origin

import black
from loguru import logger
from PyQt5.QtCore import QIODevice, QSaveFile
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefinedType
from qfluentwidgets import (
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    NavigationInterface,
    NavigationItemPosition,
    SegmentedWidget,
    TogglePushButton,
)
from chemunited.core.utils import ChemQuantityValidator, ChemUnitQuantity
from chemunited.qt.utils.files import load_class
from chemunited.qt.shared.editor.base import EditorBase
from chemunited.qt.shared.editor.parameters.list import ParameterListWidget
from chemunited.qt.shared.icon import OrchestratorIcon
from chemunited.qt.shared.widgets.base_mode_editor.cards.builder_models import (
    BasicVariableBuildMode,
    BoolVariableBuildMode,
    ChoiceVariableBuildMode,
    FloatVariableBuildMode,
    IntVariableBuildMode,
    ListVariableBuildMode,
    PhysicalQuantitiesMode,
    StringVariableBuildMode,
)


# ---------------------------------------------------------------------------
# Helper — map one FieldInfo to the correct *BuildMode
# ---------------------------------------------------------------------------


def field_info_to_build_mode(
    field_name: str, fi: FieldInfo
) -> BasicVariableBuildMode | None:
    """
    Convert a single Pydantic FieldInfo into the matching *BuildMode instance.
    Returns None for private fields (name starts with '_') and unsupported types.
    """
    if field_name.startswith("_"):
        return None

    extra: dict[str, Any] = fi.json_schema_extra or {}
    base_kwargs: dict[str, Any] = {
        "name": field_name,
        "title": fi.title or "",
        "description": fi.description or "",
        "group": extra.get("group", "General"),
        "editable": extra.get("editable", True),
        "visible": extra.get("visible", True),
    }

    annotation = fi.annotation

    # Unwrap Annotated[X, ...] if present
    if get_origin(annotation) is Annotated:
        args = get_args(annotation)
        inner_type = args[0]
        ann_metadata = list(args[1:])
    else:
        inner_type = annotation
        ann_metadata = list(fi.metadata)

    # All metadata (from Annotated args + fi.metadata, de-duplicated by id)
    all_meta = ann_metadata + [m for m in fi.metadata if m not in ann_metadata]

    def _get(key: str) -> Any:
        """Extract the first metadata object that has *key* as a truthy attribute."""
        for m in all_meta:
            v = getattr(m, key, None)
            if v is not None:
                return v
        return None

    def _default(fallback: Any = None) -> Any:
        """Return fi.default if it is a real value, else call default_factory."""
        if isinstance(fi.default, PydanticUndefinedType):
            factory = getattr(fi, "default_factory", None)
            if factory is not None:
                try:
                    return factory()
                except Exception:
                    pass
            return fallback
        return fi.default

    # 1. Physical quantity: Annotated[ChemUnitQuantity, ChemQuantityValidator(...)]
    if inner_type is ChemUnitQuantity:
        validator = next(
            (m for m in all_meta if isinstance(m, ChemQuantityValidator)), None
        )
        unit = f"{validator.units:~}" if validator else "ml"
        raw_default = _default()
        if raw_default is not None and hasattr(raw_default, "magnitude"):
            default_str = f"{raw_default.magnitude:g} {unit}"
        else:
            default_str = f"0 {unit}"
        return PhysicalQuantitiesMode(unit=unit, default=default_str, **base_kwargs)

    ann = inner_type

    # 2. Choice (str with Options in json_schema_extra)
    if ann is str and extra.get("Options"):
        options = list(extra.get("Options", []))
        return ChoiceVariableBuildMode(
            default=str(_default("")), Options=options, **base_kwargs
        )

    # 3. int
    if ann is int:
        kwargs: dict[str, Any] = {}
        ge = _get("ge")
        le = _get("le")
        if ge is not None:
            kwargs["ge"] = int(ge)
        if le is not None:
            kwargs["le"] = int(le)
        return IntVariableBuildMode(default=int(_default(0)), **base_kwargs, **kwargs)

    # 4. float
    if ann is float:
        kwargs = {}
        ge = _get("ge")
        le = _get("le")
        if ge is not None:
            kwargs["ge"] = float(ge)
        if le is not None:
            kwargs["le"] = float(le)
        return FloatVariableBuildMode(default=float(_default(0.0)), **base_kwargs, **kwargs)

    # 5. bool
    if ann is bool:
        return BoolVariableBuildMode(default=bool(_default(False)), **base_kwargs)

    # 6. list / list[X]
    if ann is list or get_origin(ann) is list:
        raw = _default([])
        default_list = list(raw) if isinstance(raw, (list, tuple)) else []
        return ListVariableBuildMode(default=default_list, **base_kwargs)

    # 7. str (plain, no Options)
    if ann is str:
        kwargs = {}
        min_len = _get("min_length")
        max_len = _get("max_length")
        pattern = _get("pattern") or ""
        if min_len is not None:
            kwargs["min_length"] = int(min_len)
        if max_len is not None:
            kwargs["max_length"] = int(max_len)
        if pattern:
            kwargs["pattern"] = str(pattern)
        return StringVariableBuildMode(default=str(_default("")), **base_kwargs, **kwargs)

    logger.warning(
        f"field_info_to_build_mode: unsupported type {ann!r} for field {field_name!r}"
    )
    return None


# ---------------------------------------------------------------------------
# Script editor widget
# ---------------------------------------------------------------------------


class Editor(EditorBase):
    """QsciScintilla editor — loads *path* on construction."""

    def __init__(self, path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent=parent, path=path)
        self._load_content()


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------


class MainParametersEditor(QMainWindow):
    """
    Parameters-file editor.

    Parameters
    ----------
    path:
        Path to the Python file that contains the ``BaseModeParameters``
        subclass to edit (e.g. ``parameters.py``).
    class_name:
        Name of the class inside that file, e.g. ``"ProcessParameters"``.
    parent:
        Qt parent widget.
    """

    def __init__(
        self,
        path: Path,
        class_name: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._path       = path
        self._class_name = class_name

        self.setWindowTitle(f"Parameters Editor — {path.name}  ·  {class_name}")
        self.setWindowIcon(QIcon(OrchestratorIcon.CHEMUNITED.path()))
        self.resize(900, 650)
        self.setMinimumSize(650, 500)

        # Resolve base class name from the file so build_source() emits the
        # correct class header (e.g. BaseModel vs BaseModeParameters).
        try:
            _klass = load_class(self._path, self._class_name)
            _base_class_name = _klass.__bases__[0].__name__
        except Exception:
            _base_class_name = "BaseModel"

        self.param_list = ParameterListWidget(
            class_name=class_name,
            base_class_name=_base_class_name,
            write_callback=self._write_to_file,
        )
        self.editor = Editor(path=path, parent=self)
        self.editor.setReadOnly(True)
        self.editor.set_autosave(False)
        self._edit_mode: bool = False

        self.navigationInterface = NavigationInterface(
            self, showMenuButton=True, collapsible=False
        )

        self._init_layout()
        self._init_navigation()
        self._load_fields_from_file()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _init_layout(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)

        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        content_area = QWidget(central)
        cl = QVBoxLayout(content_area)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)

        self.pivot = SegmentedWidget(content_area)
        self.stack = QStackedWidget(content_area)

        self.pivot.addItem(
            routeKey="params",
            text="Parameters List",
            onClick=self._show_params_tab,
        )
        self.pivot.addItem(
            routeKey="script",
            text="Script Editor",
            onClick=self._show_script_tab,
        )
        self.pivot.setCurrentItem("params")

        # Wrap editor + toggle button in a container widget
        script_container = QWidget(content_area)
        sc_layout = QVBoxLayout(script_container)
        sc_layout.setContentsMargins(0, 0, 0, 8)
        sc_layout.setSpacing(0)
        sc_layout.addWidget(self.editor, stretch=1)

        toggle_row = QWidget(script_container)
        tr_layout = QHBoxLayout(toggle_row)
        tr_layout.setContentsMargins(0, 6, 0, 0)
        self.edit_toggle = TogglePushButton(FluentIcon.EDIT, "Edit Script", toggle_row)
        self.edit_toggle.toggled.connect(self._on_toggle_edit_mode)
        tr_layout.addStretch()
        tr_layout.addWidget(self.edit_toggle)
        tr_layout.addStretch()
        sc_layout.addWidget(toggle_row)

        self.stack.addWidget(self.param_list)      # index 0
        self.stack.addWidget(script_container)     # index 1

        cl.addWidget(self.pivot)
        cl.addWidget(self.stack)

        root.addWidget(content_area, stretch=1)
        root.addWidget(self.navigationInterface)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _init_navigation(self) -> None:
        self.navigationInterface.addItem(
            routeKey="Save",
            icon=FluentIcon.SAVE,
            text="Save",
            onClick=self._save,
            selectable=False,
            position=NavigationItemPosition.BOTTOM,
            tooltip="Save",
        )
        self.navigationInterface.addItem(
            routeKey="Set Black Format",
            icon=FluentIcon.BROOM,
            text="Set Black Format",
            onClick=self._format_with_black,
            selectable=False,
            position=NavigationItemPosition.BOTTOM,
            tooltip="Format with Black",
        )

        self.navigationInterface.addItemHeader("NUMERIC")
        self.navigationInterface.addItem(
            routeKey="New integer variable",
            icon=OrchestratorIcon.INTEGER,
            text="New integer variable",
            onClick=partial(self._add_card, IntVariableBuildMode()),
            selectable=False,
            tooltip="New integer variable",
        )
        self.navigationInterface.addItem(
            routeKey="New float variable",
            icon=FluentIcon.SKIP_BACK,
            text="New float variable",
            onClick=partial(self._add_card, FloatVariableBuildMode()),
            selectable=False,
            tooltip="New float variable",
        )
        self.navigationInterface.addItem(
            routeKey="New physical quantity",
            icon=OrchestratorIcon.MEASURE,
            text="New physical quantity",
            onClick=partial(self._add_card, PhysicalQuantitiesMode()),
            selectable=False,
            tooltip="New physical quantity",
        )

        self.navigationInterface.addItemHeader("TEXT")
        self.navigationInterface.addItem(
            routeKey="New string variable",
            icon=OrchestratorIcon.STRING,
            text="New string variable",
            onClick=partial(self._add_card, StringVariableBuildMode()),
            selectable=False,
            tooltip="New string variable",
        )
        self.navigationInterface.addItem(
            routeKey="New array variable",
            icon=OrchestratorIcon.LIST,
            text="New array variable",
            onClick=partial(self._add_card, ListVariableBuildMode()),
            selectable=False,
            tooltip="New array variable",
        )
        self.navigationInterface.addItem(
            routeKey="New choice variable",
            icon=OrchestratorIcon.CHOICES,
            text="New choice variable",
            onClick=partial(self._add_card, ChoiceVariableBuildMode()),
            selectable=False,
            tooltip="New choice variable",
        )
        self.navigationInterface.addItem(
            routeKey="New bool variable",
            icon=OrchestratorIcon.BOOLEAN,
            text="New bool variable",
            onClick=partial(self._add_card, BoolVariableBuildMode()),
            selectable=False,
            tooltip="New bool variable",
        )

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _show_params_tab(self) -> None:
        self.stack.setCurrentIndex(0)
        self.editor.set_autosave(False)

    def _show_script_tab(self) -> None:
        self.stack.setCurrentIndex(1)
        self._reset_to_readonly()

    def _add_card(self, mode: BasicVariableBuildMode) -> None:
        self.param_list.add_card(copy.deepcopy(mode))
        self.pivot.setCurrentItem("params")
        self.stack.setCurrentIndex(0)

    def _save(self) -> None:
        if not self.param_list.validate_all():
            InfoBar.error(
                title="Validation error",
                content="Fix the highlighted fields before saving.",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=4000,
            )
            return
        source = self.param_list.build_source()
        if source:
            self._write_to_file(source)
            self._format_with_black()

    def _format_with_black(self) -> None:
        try:
            code = self.editor.text()
            formatted = black.format_str(code, mode=black.Mode())
            if formatted != code:
                cursor_pos = self.editor.getCursorPosition()
                self._write_to_file_raw(formatted)
                self.editor.setText(formatted)
                self.editor.setCursorPosition(*cursor_pos)
        except black.NothingChanged:
            pass
        except Exception as exc:
            logger.opt(exception=exc).error(
                "Black formatting failed — see the logging window for details."
            )

    # ------------------------------------------------------------------
    # File I/O
    # ------------------------------------------------------------------

    def _reset_to_readonly(self) -> None:
        """Enter (or re-enter) the Script Editor tab in read-only mode."""
        self._edit_mode = False
        self.editor.setReadOnly(True)
        self.editor.set_autosave(False)
        self.edit_toggle.setChecked(False)
        self.edit_toggle.setIcon(FluentIcon.EDIT)
        self.edit_toggle.setText("Edit Script")
        self.pivot.setEnabled(True)

    def _on_toggle_edit_mode(self, checked: bool) -> None:
        self._edit_mode = checked
        if checked:
            self.editor.setReadOnly(False)
            self.editor.set_autosave(True)
            self.edit_toggle.setIcon(FluentIcon.VIEW)
            self.edit_toggle.setText("Read Only")
            self.pivot.setEnabled(False)
        else:
            # Flush editor to disk before validating
            self.editor.save_now()
            ok, err = self._validate_file()
            if not ok:
                # Stay in edit mode — revert the toggle without re-firing this slot
                self.edit_toggle.blockSignals(True)
                self.edit_toggle.setChecked(True)
                self.edit_toggle.setIcon(FluentIcon.VIEW)
                self.edit_toggle.setText("Read Only")
                self.edit_toggle.blockSignals(False)
                self._edit_mode = True
                InfoBar.error(
                    title="Invalid file — cannot leave edit mode",
                    content=err,
                    parent=self,
                    position=InfoBarPosition.TOP,
                    duration=8000,
                )
                return
            self.editor.setReadOnly(True)
            self.editor.set_autosave(False)
            self.edit_toggle.setIcon(FluentIcon.EDIT)
            self.edit_toggle.setText("Edit Script")
            self.pivot.setEnabled(True)
            self._reload_params_from_file()

    def _validate_file(self) -> tuple[bool, str]:
        """Return (True, '') if the file can be imported and the class is a valid
        Pydantic model, otherwise (False, error_message)."""
        try:
            klass = load_class(self._path, self._class_name)
            # Force full schema rebuild — catches lazy annotation errors that
            # model_fields alone misses (e.g. when __future__ annotations is used).
            klass.model_rebuild(force=True)
            return True, ""
        except Exception as exc:
            logger.warning(f"Validation failed for {self._class_name}: {exc}")
            return False, str(exc)

    def _reload_params_from_file(self) -> None:
        """Clear all cards and re-populate from the current file on disk."""
        self.param_list.clear_all()
        self._load_fields_from_file()

    def _load_fields_from_file(self) -> None:
        try:
            klass = load_class(self._path, self._class_name)
        except Exception as exc:
            logger.error(f"Could not load {self._class_name} from {self._path}: {exc}")
            InfoBar.error(
                title="Load error",
                content=f"Could not load {self._class_name}: {exc}",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=5000,
            )
            return
        self.param_list.begin_load()
        try:
            for field_name, fi in klass.model_fields.items():
                mode = field_info_to_build_mode(field_name, fi)
                if mode is not None:
                    self.param_list.add_card(mode)
        finally:
            self.param_list.end_load()

    def _write_to_file(self, class_source: str) -> None:
        """
        Splice *class_source* (field definitions only) into the original file.
        - Everything above and below the class is preserved verbatim.
        - Non-field items inside the class (methods, validators, class vars, etc.)
          are preserved and appended after the regenerated fields.
        """
        try:
            original = self._path.read_text(encoding="utf-8")
            tree = ast.parse(original)
            lines = original.splitlines(keepends=True)
            for node in tree.body:
                if isinstance(node, ast.ClassDef) and node.name == self._class_name:
                    start = node.lineno - 1   # 0-indexed, inclusive
                    end   = node.end_lineno   # 0-indexed, exclusive

                    # Collect non-field items in their original order.
                    # For decorated functions, start from the first decorator line.
                    preserved: list[str] = []
                    for item in sorted(node.body, key=lambda n: n.lineno):
                        if isinstance(item, ast.AnnAssign):
                            continue
                        dec_list = getattr(item, "decorator_list", [])
                        item_start = (dec_list[0].lineno - 1) if dec_list else (item.lineno - 1)
                        item_end   = item.end_lineno
                        seg = "".join(lines[item_start:item_end]).rstrip()
                        if seg:
                            preserved.append(seg)

                    new_class = class_source.rstrip("\n")
                    if preserved:
                        new_class += "\n\n" + "\n\n".join(preserved) + "\n"
                    else:
                        new_class += "\n"

                    new_text = (
                        "".join(lines[:start])
                        + new_class
                        + "".join(lines[end:])
                    )
                    break
            else:
                logger.warning(
                    f"Class {self._class_name!r} not found in {self._path} — "
                    "file not modified."
                )
                return
            self._write_to_file_raw(new_text)
            self.editor.setText(new_text)
        except Exception as exc:
            logger.opt(exception=exc).error(f"Write failed for {self._path}")

    def _write_to_file_raw(self, content: str) -> None:
        """Atomic write of *content* to disk without touching the editor."""
        f = QSaveFile(str(self._path))
        if f.open(QIODevice.WriteOnly):
            f.write(content.encode("utf-8"))
            if not f.commit():
                logger.error(f"QSaveFile commit failed for {self._path}: {f.errorString()}")
        else:
            logger.error(f"QSaveFile could not open {self._path}: {f.errorString()}")



if __name__ == "__main__":
    from PyQt5.QtWidgets import QApplication
    import sys
    app = QApplication(sys.argv)
    window = MainParametersEditor(
        path=Path(__file__).parent / "example.py",
        class_name="ProcessParameters",
    )
    window.show()
    sys.exit(app.exec())
    