"""Draggable list of field names from a Pydantic model class."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger
from PyQt5.QtCore import QMimeData, Qt
from PyQt5.QtGui import QDrag, QIcon
from PyQt5.QtWidgets import QAbstractItemView, QListWidgetItem, QVBoxLayout, QWidget
from qfluentwidgets import FluentIcon, ListWidget

from chemunited.shared.editor.parameters.main import field_info_to_build_mode
from chemunited.shared.icon import OrchestratorIcon
from chemunited.shared.widgets.base_mode_editor.cards.builder_models import (
    BasicVariableBuildMode,
    BoolVariableBuildMode,
    ChoiceVariableBuildMode,
    FloatVariableBuildMode,
    IntVariableBuildMode,
    ListVariableBuildMode,
    PhysicalQuantitiesMode,
    StringVariableBuildMode,
)
from chemunited.utils.files import load_class


def _build_mode_icon(mode: BasicVariableBuildMode | None) -> QIcon:
    if isinstance(mode, IntVariableBuildMode):
        return OrchestratorIcon.INTEGER.icon()
    if isinstance(mode, FloatVariableBuildMode):
        return FluentIcon.SKIP_BACK.icon()
    if isinstance(mode, PhysicalQuantitiesMode):
        return OrchestratorIcon.MEASURE.icon()
    if isinstance(mode, StringVariableBuildMode):
        return OrchestratorIcon.STRING.icon()
    if isinstance(mode, ListVariableBuildMode):
        return OrchestratorIcon.LIST.icon()
    if isinstance(mode, ChoiceVariableBuildMode):
        return OrchestratorIcon.CHOICES.icon()
    if isinstance(mode, BoolVariableBuildMode):
        return OrchestratorIcon.BOOLEAN.icon()
    return OrchestratorIcon.VARIABLE.icon()


class _DragListWidget(ListWidget):
    """qfluentwidgets ListWidget that exposes the dragged item as plain text."""

    MIME = "application/x-chemunited-parameter-field"
    PATH_MIME = "application/x-chemunited-parameter-source-path"

    def __init__(self, path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragOnly)
        self.setDefaultDropAction(Qt.CopyAction)  # type: ignore[attr-defined]
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self._path = path

    def startDrag(self, _supported_actions) -> None:  # type: ignore[override]
        item = self.currentItem()
        if item is None:
            return
        line_tree = "self.config."
        if self._path.name == "main_parameters.py":
            line_tree = "self.main_parameters."

        param_line = f"{line_tree}{item.text()}"

        mime = QMimeData()
        mime.setData(self.MIME, param_line.encode("utf-8"))
        mime.setData(self.PATH_MIME, str(self._path).encode("utf-8"))
        mime.setText(param_line)
        drag = QDrag(self)
        drag.setMimeData(mime)

        item_rect = self.visualItemRect(item)
        viewport = self.viewport()
        pixmap = viewport.grab(item_rect) if viewport is not None else None
        if pixmap is not None and not pixmap.isNull():
            drag.setPixmap(pixmap)
            drag.setHotSpot(item_rect.topLeft())

        drag.exec_(Qt.CopyAction)  # type: ignore[attr-defined]


class ParameterDragableList(QWidget):
    """Read-only draggable list of Pydantic model field names.

    Each item shows the field's type icon and its name. Items can be dragged
    into a script or text editor as plain text, and also carry the custom
    MIME type ``ParameterDragableList.MIME`` for structured drop handlers.
    """

    MIME = _DragListWidget.MIME
    PATH_MIME = _DragListWidget.PATH_MIME

    def __init__(
        self,
        path: Path,
        class_name: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._path = path
        self._class_name = class_name

        self._list = _DragListWidget(path=self._path, parent=self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._list)

        self._populate()

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
            return None

    def _populate(self) -> None:
        model_class = self._load_model_class()
        if model_class is None:
            return
        for field_name, field_info in model_class.model_fields.items():
            mode = field_info_to_build_mode(field_name, field_info)
            item = QListWidgetItem(_build_mode_icon(mode), field_name)
            self._list.addItem(item)

    def reload(self) -> None:
        self._list.clear()
        self._populate()


if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv)
    window = ParameterDragableList(
        path=Path(__file__).parent / "example.py",
        class_name="ProcessParameters",
    )
    window.show()
    sys.exit(app.exec())
