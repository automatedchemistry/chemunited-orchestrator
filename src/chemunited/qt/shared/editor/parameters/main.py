"""Card-based parameters editor with live writes on valid user changes."""

from __future__ import annotations

import ast
import copy
from functools import partial
from pathlib import Path
from typing import Annotated, Any, get_args, get_origin

from loguru import logger
from pydantic.config import JsonDict
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefinedType
from PyQt5.QtCore import QIODevice, QSaveFile
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QMainWindow, QWidget
from qfluentwidgets import (
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    NavigationInterface,
)

from chemunited_core.utils import ChemQuantityValidator, ChemUnitQuantity
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
from chemunited.qt.utils.files import load_class

QIODEVICE_TEXT = getattr(QIODevice, "Text")
QIODEVICE_WRITE_ONLY = getattr(QIODevice, "WriteOnly")


def _unwrap_annotation(fi: FieldInfo) -> tuple[Any, list[Any]]:
    """Return the core annotation and merged metadata for a field."""
    annotation = fi.annotation
    metadata: list[Any] = []

    if get_origin(annotation) is Annotated:
        args = get_args(annotation)
        annotation = args[0]
        metadata.extend(args[1:])

    metadata.extend(meta for meta in fi.metadata if meta not in metadata)
    return annotation, metadata


def _metadata_value(metadata: list[Any], key: str) -> Any:
    for meta in metadata:
        value = getattr(meta, key, None)
        if value is not None:
            return value
    return None


def _field_default(fi: FieldInfo, fallback: Any = None) -> Any:
    if not isinstance(fi.default, PydanticUndefinedType):
        return fi.default

    default_factory = getattr(fi, "default_factory", None)
    if default_factory is None:
        return fallback

    try:
        return default_factory()
    except Exception:
        return fallback


def _field_extra_dict(fi: FieldInfo) -> JsonDict:
    extras = fi.json_schema_extra
    if isinstance(extras, dict):
        return extras
    return {}


def field_info_to_build_mode(
    field_name: str,
    field_info: FieldInfo,
) -> BasicVariableBuildMode | None:
    """Map one Pydantic field into the matching build-mode model."""
    if field_name.startswith("_"):
        return None

    extra = _field_extra_dict(field_info)
    annotation, metadata = _unwrap_annotation(field_info)
    title = field_info.title or ""
    description = field_info.description or ""
    group = str(extra.get("group", "General"))
    editable = bool(extra.get("editable", True))
    visible = bool(extra.get("visible", True))

    if annotation is ChemUnitQuantity:
        validator = next(
            (meta for meta in metadata if isinstance(meta, ChemQuantityValidator)),
            None,
        )
        unit = f"{validator.units:~}" if validator else "ml"
        default = _field_default(field_info)
        if default is not None and hasattr(default, "magnitude"):
            default_text = f"{default.magnitude:g} {unit}"
        else:
            default_text = f"0 {unit}"
        return PhysicalQuantitiesMode(
            name=field_name,
            title=title,
            description=description,
            group=group,
            editable=editable,
            visible=visible,
            unit=unit,
            default=default_text,
        )

    options_value = extra.get("Options", [])
    options = (
        [str(option) for option in options_value]
        if isinstance(options_value, list)
        else []
    )
    if annotation is str and options:
        default = _field_default(field_info, "")
        return ChoiceVariableBuildMode(
            name=field_name,
            title=title,
            description=description,
            group=group,
            editable=editable,
            visible=visible,
            default=str(default),
            Options=options,
        )

    if annotation is int:
        ge = _metadata_value(metadata, "ge")
        le = _metadata_value(metadata, "le")
        return IntVariableBuildMode(
            name=field_name,
            title=title,
            description=description,
            group=group,
            editable=editable,
            visible=visible,
            default=int(_field_default(field_info, 0)),
            ge=int(ge) if ge is not None else 0,
            le=int(le) if le is not None else 100,
        )

    if annotation is float:
        ge = _metadata_value(metadata, "ge")
        le = _metadata_value(metadata, "le")
        return FloatVariableBuildMode(
            name=field_name,
            title=title,
            description=description,
            group=group,
            editable=editable,
            visible=visible,
            default=float(_field_default(field_info, 0.0)),
            ge=float(ge) if ge is not None else 0.0,
            le=float(le) if le is not None else 100.0,
        )

    if annotation is bool:
        return BoolVariableBuildMode(
            name=field_name,
            title=title,
            description=description,
            group=group,
            editable=editable,
            visible=visible,
            default=bool(_field_default(field_info, False)),
            on_text=str(extra.get("on_text", "On")),
            off_text=str(extra.get("off_text", "Off")),
        )

    if annotation is list or get_origin(annotation) is list:
        default = _field_default(field_info, [])
        default_list = list(default) if isinstance(default, (list, tuple)) else []
        return ListVariableBuildMode(
            name=field_name,
            title=title,
            description=description,
            group=group,
            editable=editable,
            visible=visible,
            default=default_list,
        )

    if annotation is str:
        min_length = _metadata_value(metadata, "min_length")
        max_length = _metadata_value(metadata, "max_length")
        pattern = _metadata_value(metadata, "pattern") or ""
        return StringVariableBuildMode(
            name=field_name,
            title=title,
            description=description,
            group=group,
            editable=editable,
            visible=visible,
            default=str(_field_default(field_info, "")),
            pattern=str(pattern),
            min_length=int(min_length) if min_length is not None else 0,
            max_length=int(max_length) if max_length is not None else 50,
        )

    logger.warning(
        f"field_info_to_build_mode: unsupported type {annotation!r} for field {field_name!r}",
    )
    return None


class MainParametersEditor(QMainWindow):
    """Single-view parameter editor focused on the card list."""

    def __init__(
        self,
        path: Path,
        class_name: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._path = path
        self._class_name = class_name

        self.setWindowTitle(f"Parameters Editor - {path.name} - {class_name}")
        self.setWindowIcon(QIcon(OrchestratorIcon.CHEMUNITED.path()))
        self.resize(900, 650)
        self.setMinimumSize(650, 500)

        self.param_list = ParameterListWidget(
            class_name=class_name,
            write_callback=self._on_user_change,
            parent=self,
        )
        self.navigationInterface = NavigationInterface(
            self,
            showMenuButton=True,
            collapsible=False,
        )

        self._init_layout()
        self._init_navigation()

        model_class = self._load_model_class()
        if model_class is not None:
            self._populate_cards(model_class)

    def _init_layout(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)

        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.param_list, stretch=1)
        layout.addWidget(self.navigationInterface)

        self.param_list.setFrameShape(QFrame.NoFrame)

    def _init_navigation(self) -> None:
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

    def _load_model_class(self) -> type[Any] | None:
        try:
            model_class = load_class(self._path, self._class_name)
            model_rebuild = getattr(model_class, "model_rebuild", None)
            if callable(model_rebuild):
                model_rebuild(force=True)
            return model_class
        except Exception as exc:
            logger.opt(exception=exc).error(
                f"Could not load {self._class_name!r} from {self._path}."
            )
            InfoBar.error(
                title="Load error",
                content=f"Could not load {self._class_name}: {exc}",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=5000,
            )
            return None

    def _populate_cards(self, model_class: type[Any]) -> None:
        base_class_name = model_class.__bases__[0].__name__
        self.param_list.set_base_class_name(base_class_name)

        with self.param_list.suspend_writes():
            self.param_list.clear_all()
            for field_name, field_info in model_class.model_fields.items():
                mode = field_info_to_build_mode(field_name, field_info)
                if mode is not None:
                    self.param_list.add_card(mode)

    def _add_card(self, mode: BasicVariableBuildMode) -> None:
        self.param_list.add_card(copy.deepcopy(mode))

    def _on_user_change(self, class_source: str) -> None:
        self._write_to_file(class_source)

    def _write_to_file(self, class_source: str) -> None:
        """Splice the rendered class definition back into the original file."""
        try:
            original = self._path.read_text(encoding="utf-8")
            tree = ast.parse(original)
            lines = original.splitlines(keepends=True)

            for node in tree.body:
                if not isinstance(node, ast.ClassDef) or node.name != self._class_name:
                    continue

                start = node.lineno - 1
                end = node.end_lineno
                preserved: list[str] = []

                for item in sorted(node.body, key=lambda child: child.lineno):
                    if isinstance(item, ast.AnnAssign):
                        continue

                    decorators = getattr(item, "decorator_list", [])
                    item_start = (
                        decorators[0].lineno - 1 if decorators else item.lineno - 1
                    )
                    item_end = item.end_lineno
                    segment = "".join(lines[item_start:item_end]).rstrip()
                    if segment:
                        preserved.append(segment)

                new_class = class_source.rstrip("\n")
                if preserved:
                    new_class += "\n\n" + "\n\n".join(preserved) + "\n"
                else:
                    new_class += "\n"

                new_text = "".join(lines[:start]) + new_class + "".join(lines[end:])
                self._write_to_file_raw(new_text)
                return

            logger.warning(
                f"Class {self._class_name!r} not found in {self._path}; file was not modified."
            )
        except Exception as exc:
            logger.opt(exception=exc).error("Failed to write parameters file.")

    def _write_to_file_raw(self, content: str) -> None:
        file = QSaveFile(str(self._path))
        if not file.open(QIODEVICE_WRITE_ONLY | QIODEVICE_TEXT):
            logger.error(f"QSaveFile could not open {self._path}: {file.errorString()}")
            return

        file.write(content.encode("utf-8"))
        if not file.commit():
            logger.error(
                f"QSaveFile commit failed for {self._path}: {file.errorString()}"
            )


if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv)
    window = MainParametersEditor(
        path=Path(__file__).parent / "example.py",
        class_name="MainParameter",
    )
    window.show()
    sys.exit(app.exec())
