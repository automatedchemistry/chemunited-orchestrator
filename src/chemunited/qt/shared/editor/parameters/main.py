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
  - The source is written back to ``path`` atomically.
  - The Script Editor tab is updated to reflect the new content.
"""

from __future__ import annotations

import copy
import importlib.util
import typing
from functools import partial
from pathlib import Path
from typing import Any, get_args, get_origin

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
from pydantic import BaseModel
from pydantic.fields import FieldInfo
from qfluentwidgets import (
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    NavigationInterface,
    NavigationItemPosition,
    SegmentedWidget,
)

from chemunited.qt.shared.editor.base import EditorBase
from chemunited.qt.shared.editor.parameters.list import ParameterListWidget
from chemunited.qt.shared.icon import OrchestratorIcon
from chemunited.qt.shared.widgets.base_mode_editor.cards.builder_models import (
    BasicVariableBuildMode,
    ChoiceVariableBuildMode,
    FloatVariableBuildMode,
    IntVariableBuildMode,
    ListVariableBuildMode,
    PhysicalQuantitiesMode,
    StringVariableBuildMode,
)

try:
    from chemunited.core.utils.internal_quantity import ChemUnitQuantity
except Exception:
    ChemUnitQuantity = None  # type: ignore[assignment,misc]


# ---------------------------------------------------------------------------
# Field → BuildMode mapper
# ---------------------------------------------------------------------------


def _bound(fi: FieldInfo, key: str) -> Any:
    """Extract ge/le/min_length/max_length from pydantic field metadata."""
    for meta in fi.metadata:
        v = getattr(meta, key, None)
        if v is not None:
            return v
    return None


def _is_chem_quantity(annotation: Any) -> bool:
    """Return True if the annotation resolves to ChemUnitQuantity."""
    if ChemUnitQuantity is None:
        return False
    if annotation is ChemUnitQuantity:
        return True
    # Annotated[ChemUnitQuantity, ChemQuantityValidator(...)]
    if get_origin(annotation) is typing.Annotated:
        args = get_args(annotation)
        if args and args[0] is ChemUnitQuantity:
            return True
    return False


def _resolve_annotation(annotation: Any) -> Any:
    """
    Unwrap Annotated[X, ...] to X, so we can do clean isinstance checks.
    Returns the annotation unchanged if it is not Annotated.
    """
    if get_origin(annotation) is typing.Annotated:
        return get_args(annotation)[0]
    return annotation


def _has_options(fi: FieldInfo) -> bool:
    extra = fi.json_schema_extra or {}
    return bool(extra.get("Options"))


def field_info_to_build_mode(
    field_name: str, fi: FieldInfo
) -> BasicVariableBuildMode | None:
    """
    Map one Pydantic FieldInfo (from a user's BaseModeParameters subclass)
    to the matching ``*BuildMode`` instance pre-filled with the field's
    current values.

    Returns ``None`` for private/hidden fields (names starting with ``_``).
    """
    if field_name.startswith("_"):
        return None

    annotation = fi.annotation
    extra      = fi.json_schema_extra or {}
    default    = fi.default
    title      = fi.title or ""
    description = fi.description or ""
    group      = extra.get("group", "General")
    editable   = extra.get("editable", True)
    visible    = extra.get("visible", True)

    base = dict(
        name=field_name,
        title=title,
        description=description,
        group=group,
        editable=editable,
        visible=visible,
    )

    # ── ChemUnitQuantity ──────────────────────────────────────────────
    if _is_chem_quantity(annotation):
        default_str = str(default) if default is not None else "0 ml"
        return PhysicalQuantitiesMode(**base, default=default_str)

    core = _resolve_annotation(annotation)

    # ── choice (str with Options) ─────────────────────────────────────
    if core is str and _has_options(fi):
        options = extra.get("Options", [])
        default_val = default if isinstance(default, str) else (options[0] if options else "")
        return ChoiceVariableBuildMode(**base, default=default_val, Options=options)

    # ── int ───────────────────────────────────────────────────────────
    if core is int:
        ge = _bound(fi, "ge")
        le = _bound(fi, "le")
        return IntVariableBuildMode(
            **base,
            default=int(default) if default is not None else 0,
            ge=int(ge) if ge is not None else 0,
            le=int(le) if le is not None else 100,
        )

    # ── float ─────────────────────────────────────────────────────────
    if core is float:
        ge = _bound(fi, "ge")
        le = _bound(fi, "le")
        return FloatVariableBuildMode(
            **base,
            default=float(default) if default is not None else 0.0,
            ge=float(ge) if ge is not None else 0.0,
            le=float(le) if le is not None else 100.0,
        )

    # ── bool ──────────────────────────────────────────────────────────
    if core is bool:
        # reuse StringVariableBuildMode is wrong — bool needs its own card.
        # For now map to IntVariableBuildMode with range 0-1 as a fallback
        # until BoolVariableBuildMode is added to builder_models.
        # If you have BoolVariableBuildMode, swap here.
        return IntVariableBuildMode(
            **base,
            default=1 if default else 0,
            ge=0,
            le=1,
        )

    # ── list ──────────────────────────────────────────────────────────
    if core is list or (get_origin(core) is list):
        items: list = []
        if callable(fi.default_factory):       # type: ignore[attr-defined]
            items = fi.default_factory()
        elif isinstance(default, list):
            items = default
        return ListVariableBuildMode(**base, default=items)

    # ── str (plain, no Options) ───────────────────────────────────────
    if core is str:
        ge = _bound(fi, "min_length")
        le = _bound(fi, "max_length")
        pattern = ""
        for meta in fi.metadata:
            p = getattr(meta, "pattern", None)
            if p:
                pattern = p
                break
        return StringVariableBuildMode(
            **base,
            default=str(default) if default is not None else "",
            pattern=pattern,
            min_length=int(ge) if ge is not None else 0,
            max_length=int(le) if le is not None else 50,
        )

    # ── unrecognised — skip ───────────────────────────────────────────
    logger.warning(
        f"field_info_to_build_mode: cannot map field '{field_name}'"
        f" with annotation {annotation!r} — skipped."
    )
    return None


# ---------------------------------------------------------------------------
# importlib loader
# ---------------------------------------------------------------------------


def load_class_from_file(file_path: Path, class_name: str) -> type[BaseModel]:
    """
    Dynamically load *class_name* from *file_path* using importlib.

    Raises
    ------
    AttributeError
        If the class is not found in the module.
    """
    spec = importlib.util.spec_from_file_location(class_name, file_path)
    module = importlib.util.module_from_spec(spec)   # type: ignore[arg-type]
    spec.loader.exec_module(module)                  # type: ignore[union-attr]
    return getattr(module, class_name)


# ---------------------------------------------------------------------------
# Code editor
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

        self.param_list = ParameterListWidget(
            class_name=class_name,
            write_callback=self._write_to_file,
            parent=self,
        )
        self.editor = Editor(path=path, parent=self)

        self.navigationInterface = NavigationInterface(
            self, showMenuButton=True, collapsible=False
        )

        self._init_layout()
        self._init_navigation()

        # Load the class and populate cards automatically.
        self._load_fields_from_file()

    # ------------------------------------------------------------------
    # Startup: load existing fields
    # ------------------------------------------------------------------

    def _load_fields_from_file(self) -> None:
        """
        Import *class_name* from *path*, walk its model_fields, and build
        one card per field.  Private fields (name starts with ``_``) are
        skipped automatically by ``field_info_to_build_mode``.
        """
        try:
            cls = load_class_from_file(self._path, self._class_name)
        except Exception as exc:
            logger.opt(exception=exc).error(
                f"Could not load '{self._class_name}' from {self._path}."
            )
            InfoBar.error(
                title="Load error",
                content=f"Could not load class '{self._class_name}' from {self._path.name}.",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=6000,
            )
            return

        for field_name, fi in cls.model_fields.items():
            mode = field_info_to_build_mode(field_name, fi)
            if mode is not None:
                self.param_list.add_card(mode)

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
            onClick=lambda: self.stack.setCurrentIndex(0),
        )
        self.pivot.addItem(
            routeKey="script",
            text="Script Editor",
            onClick=lambda: self.stack.setCurrentIndex(1),
        )
        self.pivot.setCurrentItem("params")

        self.stack.addWidget(self.param_list)   # index 0
        self.stack.addWidget(self.editor)       # index 1

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

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _add_card(self, mode: BaseModel) -> None:
        """Insert a blank card with default values — no dialog."""
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

    def _format_with_black(self) -> None:
        try:
            code = self.editor.text()
            formatted = black.format_str(code, mode=black.Mode())
            if formatted != code:
                cursor_pos = self.editor.getCursorPosition()
                self._write_to_file(formatted)
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

    def _write_to_file(self, source: str) -> None:
        """Atomic write to *path* + live-update the Script Editor tab."""
        try:
            sf = QSaveFile(str(self._path.absolute()))
            if not sf.open(QIODevice.WriteOnly | QIODevice.Text):   # type: ignore[attr-defined]
                logger.error(f"Cannot open {self._path}: {sf.errorString()}")
                return
            sf.write(source.encode("utf-8"))
            if not sf.commit():
                logger.error(f"Write failed for {self._path}: {sf.errorString()}")
                return
            # Keep the Script Editor tab in sync.
            self.editor.setText(source)
        except Exception as exc:
            logger.opt(exception=exc).error("Failed to write parameters file.")
