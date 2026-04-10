"""Card widgets for the parameters editor."""

from __future__ import annotations

import ast
from typing import Any, get_origin

from pydantic import ValidationError
from pydantic.fields import FieldInfo
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    DoubleSpinBox,
    FluentIcon,
    LineEdit,
    SpinBox,
    SwitchButton,
    TransparentToolButton,
)

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
# Type metadata
# ---------------------------------------------------------------------------

_BADGE: dict[str, tuple[str, str]] = {
    "IntVariableBuildMode": ("#E6F1FB", "#185FA5"),
    "FloatVariableBuildMode": ("#E1F5EE", "#0F6E56"),
    "PhysicalQuantitiesMode": ("#FBEAF0", "#993556"),
    "StringVariableBuildMode": ("#FAEEDA", "#854F0B"),
    "ListVariableBuildMode": ("#FAECE7", "#993C1D"),
    "ChoiceVariableBuildMode": ("#F1EFE8", "#5F5E5A"),
    "BoolVariableBuildMode": ("#EEEDFE", "#534AB7"),
}

_SHORT: dict[str, str] = {
    "IntVariableBuildMode": "int",
    "FloatVariableBuildMode": "float",
    "PhysicalQuantitiesMode": "qty",
    "StringVariableBuildMode": "str",
    "ListVariableBuildMode": "list",
    "ChoiceVariableBuildMode": "choice",
    "BoolVariableBuildMode": "bool",
}

# These fields are rendered in the dedicated bottom section, not as body rows.
_BEHAVIOR_FIELDS = {"editable", "visible"}
_ORG_FIELDS = {"group"}


def _field_extra(field_info: FieldInfo) -> dict[str, Any]:
    extra = field_info.json_schema_extra
    return extra if isinstance(extra, dict) else {}


def _is_list_annotation(annotation: Any) -> bool:
    return annotation is list or get_origin(annotation) is list


# ---------------------------------------------------------------------------
# Code generator
# ---------------------------------------------------------------------------


def generate_field_code(mode: BasicVariableBuildMode) -> str:
    """
    Produce the Python source line(s) for one Field() definition.

    Example output for an IntVariableBuildMode::

        repetitions: int = Field(
            title="Repetitions",
            description="Number of repeats",
            default=3,
            ge=1,
            le=20,
            json_schema_extra={"group": "General", "editable": True, "visible": True},
        )
    """
    v = mode.model_dump()

    name: str = v.get("name", "x")
    title: str = v.get("title", "")
    description: str = v.get("description", "")
    default = v.get("default")
    group: str = v.get("group", "General")
    editable: bool = v.get("editable", True)
    visible: bool = v.get("visible", True)

    # ── Python type annotation ──────────────────────────────────────────
    if isinstance(mode, IntVariableBuildMode):
        annotation = "int"
    elif isinstance(mode, FloatVariableBuildMode):
        annotation = "float"
    elif isinstance(mode, PhysicalQuantitiesMode):
        unit = v.get("unit", "ml")
        annotation = f'Annotated[ChemUnitQuantity, ChemQuantityValidator("{unit}")]'
        default_repr = f'ChemUnitQuantity("{default}")'
    elif isinstance(mode, StringVariableBuildMode):
        annotation = "str"
    elif isinstance(mode, ListVariableBuildMode):
        annotation = "list"
    elif isinstance(mode, ChoiceVariableBuildMode):
        annotation = "str"
    elif isinstance(mode, BoolVariableBuildMode):
        annotation = "bool"
    else:
        annotation = "Any"

    # ── default representation ──────────────────────────────────────────
    if not isinstance(mode, PhysicalQuantitiesMode):
        if isinstance(default, str):
            default_repr = f'"{default}"'
        elif isinstance(default, bool):
            default_repr = "True" if default else "False"
        elif isinstance(default, list):
            items = ", ".join(
                f'"{i}"' if isinstance(i, str) else str(i) for i in default
            )
            default_repr = f"[{items}]"
        elif default is None:
            default_repr = "None"
        else:
            default_repr = repr(default)

    # ── optional validation args ────────────────────────────────────────
    validation_lines: list[str] = []
    if isinstance(mode, (IntVariableBuildMode, FloatVariableBuildMode)):
        ge = v.get("ge")
        le = v.get("le")
        if ge is not None:
            validation_lines.append(f"    ge={ge!r},")
        if le is not None:
            validation_lines.append(f"    le={le!r},")
    elif isinstance(mode, StringVariableBuildMode):
        pattern = v.get("pattern", "")
        min_len = v.get("min_length")
        max_len = v.get("max_length")
        if pattern:
            validation_lines.append(f"    pattern={pattern!r},")
        if min_len is not None:
            validation_lines.append(f"    min_length={min_len!r},")
        if max_len is not None:
            validation_lines.append(f"    max_length={max_len!r},")
    elif isinstance(mode, ListVariableBuildMode):
        min_items = v.get("min_items")
        max_items = v.get("max_items")
        if min_items is not None:
            validation_lines.append(f"    min_items={min_items!r},")
        if max_items is not None:
            validation_lines.append(f"    max_items={max_items!r},")

    # ── json_schema_extra ───────────────────────────────────────────────
    extra: dict[str, Any] = {
        "group": group,
        "editable": editable,
        "visible": visible,
    }
    if isinstance(mode, PhysicalQuantitiesMode):
        extra["unit"] = v.get("unit", "ml")
    if isinstance(mode, ChoiceVariableBuildMode):
        options = v.get("Options", [])
        if options:
            extra["Options"] = options
    extra_repr = repr(extra)

    # ── assemble ────────────────────────────────────────────────────────
    lines = [
        f"    {name}: {annotation} = Field(",
        f'        title="{title}",',
        f'        description="{description}",',
        f"        default={default_repr},",
    ]
    lines.extend(["    " + ln for ln in validation_lines])
    lines.append(f"        json_schema_extra={extra_repr},")
    lines.append("    )")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# TypeBadge
# ---------------------------------------------------------------------------


class TypeBadge(QLabel):
    def __init__(
        self, mode: BasicVariableBuildMode, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        cls = type(mode).__name__
        bg, fg = _BADGE.get(cls, ("#eeeeee", "#333333"))
        short = _SHORT.get(cls, cls)
        self.setText(short.upper())
        self.setAlignment(Qt.AlignCenter)
        self.setFixedHeight(18)
        self.setContentsMargins(6, 0, 6, 0)
        self.setStyleSheet(
            f"background:{bg}; color:{fg}; border-radius:3px;"
            " font-size:9px; font-weight:600; letter-spacing:0.05em;"
        )


# ---------------------------------------------------------------------------
# VariableCard
# ---------------------------------------------------------------------------


class VariableCard(QWidget):
    """Expandable card for one field definition."""

    changed = pyqtSignal()
    deleted = pyqtSignal(object)
    duplicate = pyqtSignal(object)

    def __init__(
        self, mode: BasicVariableBuildMode, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.mode = mode
        self._expanded = True
        self._editors: dict[str, QWidget] = {}
        self._message: QLabel
        self._build_ui()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._frame = QFrame(self)
        self._frame.setObjectName("varCard")
        self._set_border(error=False)
        self._message = QLabel(self._frame)
        self._message.hide()
        self._message.setWordWrap(True)
        self._message.setContentsMargins(12, 0, 12, 12)
        self._message.setStyleSheet("color:#a1271f; font-size:11px; line-height:1.3;")

        fl = QVBoxLayout(self._frame)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(0)
        fl.addWidget(self._build_header())

        self._body = self._build_body()
        fl.addWidget(self._body)
        fl.addWidget(self._message)

        root.addWidget(self._frame)

    @property
    def _mode_fields(self) -> dict[str, FieldInfo]:
        return type(self.mode).model_fields

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setCursor(Qt.PointingHandCursor)

        h = QHBoxLayout(header)
        h.setContentsMargins(10, 8, 10, 8)
        h.setSpacing(8)

        drag = QLabel("⠿", header)
        drag.setStyleSheet("color:#aaa; font-size:13px;")
        h.addWidget(drag)

        h.addWidget(TypeBadge(self.mode, header))

        default_name = self._mode_fields.get("name")
        init_name = getattr(self.mode, "name", None)
        if init_name is None and default_name is not None:
            init_name = default_name.default
        init_name = init_name or "unnamed"
        self._name_label = BodyLabel(init_name, header)
        self._name_label.setStyleSheet("font-weight:500;")
        h.addWidget(self._name_label)

        h.addStretch()

        self._default_label = CaptionLabel("", header)
        self._default_label.setStyleSheet("color:#aaa; font-family:monospace;")
        h.addWidget(self._default_label)

        dup = TransparentToolButton(FluentIcon.COPY, header)
        dup.setFixedSize(24, 24)
        dup.setToolTip("Duplicate")
        dup.clicked.connect(lambda: self.duplicate.emit(self))
        h.addWidget(dup)

        btn_del = TransparentToolButton(FluentIcon.DELETE, header)
        btn_del.setFixedSize(24, 24)
        btn_del.setToolTip("Delete")
        btn_del.clicked.connect(lambda: self.deleted.emit(self))
        h.addWidget(btn_del)

        self._chevron = TransparentToolButton(FluentIcon.CHEVRON_DOWN_MED, header)
        self._chevron.setFixedSize(24, 24)
        self._chevron.clicked.connect(self._toggle_body)
        h.addWidget(self._chevron)

        header.mousePressEvent = lambda _e: self._toggle_body()
        return header

    def _build_body(self) -> QWidget:
        body = QWidget()
        body.setObjectName("cardBody")
        body.setStyleSheet("#cardBody { border-top:1px solid rgba(0,0,0,0.08); }")

        layout = QVBoxLayout(body)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)

        # Group fields by json_schema_extra["group"]
        groups: dict[str, list[tuple[str, FieldInfo]]] = {}
        for fname, finfo in self._mode_fields.items():
            if fname in _BEHAVIOR_FIELDS or fname in _ORG_FIELDS:
                continue
            grp = str(_field_extra(finfo).get("group", "General"))
            groups.setdefault(grp, []).append((fname, finfo))

        order = ["General"] + [g for g in groups if g != "General"]
        first = True
        for grp in order:
            if grp not in groups:
                continue
            if not first:
                layout.addWidget(self._section_separator(grp))
            first = False
            for fname, finfo in groups[grp]:
                row = self._make_field_row(fname, finfo)
                if row is not None:
                    layout.addWidget(row)

        layout.addWidget(self._build_behavior_section())
        return body

    # ------------------------------------------------------------------
    # Field factory
    # ------------------------------------------------------------------

    def _make_field_row(self, field_name: str, field_info: FieldInfo) -> QWidget | None:
        annotation = field_info.annotation
        default = getattr(self.mode, field_name, field_info.default)
        title = field_info.title or field_name
        editor: QWidget

        if annotation is int:
            w = SpinBox()
            ge = self._bound(field_info, "ge")
            le = self._bound(field_info, "le")
            w.setRange(
                int(ge) if ge is not None else -99_999,
                int(le) if le is not None else 99_999,
            )
            if default is not None:
                w.setValue(int(default))
            w.valueChanged.connect(self._on_change)
            editor = w

        elif annotation is float:
            w = DoubleSpinBox()
            w.setDecimals(4)
            ge = self._bound(field_info, "ge")
            le = self._bound(field_info, "le")
            w.setRange(
                float(ge) if ge is not None else -1e9,
                float(le) if le is not None else 1e9,
            )
            if default is not None:
                w.setValue(float(default))
            w.valueChanged.connect(self._on_change)
            editor = w

        elif annotation is bool:
            w = SwitchButton()
            w.setChecked(bool(default) if default is not None else False)
            w.checkedChanged.connect(self._on_change)
            editor = w

        elif _is_list_annotation(annotation):
            w = LineEdit()
            w.setPlaceholderText("Comma-separated, e.g. DCM, Toluene")
            if default is not None:
                w.setText(
                    ", ".join(str(v) for v in default)
                    if isinstance(default, list)
                    else str(default)
                )
            w.textChanged.connect(self._on_change)
            editor = w

        elif annotation is str:
            w = LineEdit()
            placeholder = str(_field_extra(field_info).get("unit", ""))
            if placeholder:
                w.setPlaceholderText(f"e.g. {placeholder}")
            if default is not None:
                w.setText(str(default))
            # name/default get dedicated handlers below that already call _emit_change
            if field_name not in ("name", "default"):
                w.textChanged.connect(self._on_change)
            editor = w

        else:
            w = LineEdit()
            if default is not None:
                w.setText(str(default))
            w.textChanged.connect(self._on_change)
            editor = w

        self._editors[field_name] = editor

        if field_name == "name" and hasattr(editor, "textChanged"):
            editor.textChanged.connect(self._on_name_changed)
        if field_name == "default" and hasattr(editor, "textChanged"):
            editor.textChanged.connect(self._on_default_changed)

        return self._labeled_row(title, editor)

    # ------------------------------------------------------------------
    # Layout helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _bound(fi: FieldInfo, key: str):
        for meta in fi.metadata:
            v = getattr(meta, key, None)
            if v is not None:
                return v
        return None

    @staticmethod
    def _labeled_row(label_text: str, widget: QWidget) -> QWidget:
        row = QWidget()
        v = QVBoxLayout(row)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(3)
        lbl = CaptionLabel(label_text, row)
        lbl.setStyleSheet(
            "font-size:10px; text-transform:uppercase;"
            " letter-spacing:0.06em; color:#999;"
        )
        v.addWidget(lbl)
        v.addWidget(widget)
        return row

    @staticmethod
    def _section_separator(title: str) -> QWidget:
        sep = QFrame()
        sep.setStyleSheet("QFrame { border-top:1px solid rgba(0,0,0,0.07); }")
        layout = QVBoxLayout(sep)
        layout.setContentsMargins(0, 8, 0, 4)
        lbl = CaptionLabel(title.upper())
        lbl.setStyleSheet(
            "font-size:9px; letter-spacing:0.1em; color:#bbb; font-weight:500;"
        )
        layout.addWidget(lbl)
        return sep

    def _build_behavior_section(self) -> QWidget:
        section = QFrame()
        section.setStyleSheet("QFrame { border-top:1px solid rgba(0,0,0,0.07); }")
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(8)

        caption = CaptionLabel("VISIBILITY & BEHAVIOR", section)
        caption.setStyleSheet(
            "font-size:9px; letter-spacing:0.1em; color:#bbb; font-weight:500;"
        )
        layout.addWidget(caption)

        # group field
        group_fi = self._mode_fields.get("group")
        if group_fi is not None:
            ge = LineEdit(section)
            ge.setText(str(getattr(self.mode, "group", group_fi.default or "General")))
            ge.textChanged.connect(self._on_change)
            self._editors["group"] = ge
            layout.addWidget(self._labeled_row("Group", ge))

        toggle_row = QHBoxLayout()
        toggle_row.setSpacing(16)

        for key in ("visible", "editable"):
            fi = self._mode_fields.get(key)
            default_val = getattr(self.mode, key, fi.default if fi else True)
            sw = SwitchButton(section)
            sw.setChecked(bool(default_val))
            sw.checkedChanged.connect(self._on_change)
            self._editors[key] = sw

            lbl = BodyLabel(key, section)
            lbl.setStyleSheet("font-size:11px;")

            pair = QHBoxLayout()
            pair.setSpacing(6)
            pair.addWidget(sw)
            pair.addWidget(lbl)
            toggle_row.addLayout(pair)

        toggle_row.addStretch()
        layout.addLayout(toggle_row)
        return section

    # ------------------------------------------------------------------
    # Frame styling
    # ------------------------------------------------------------------

    def _set_border(self, *, error: bool) -> None:
        if error:
            self._frame.setStyleSheet(
                "#varCard { border:1px solid #e8b4af;"
                " border-radius:8px; background:#fdf5f5; }"
            )
        else:
            self._frame.setStyleSheet(
                "#varCard { border:1px solid rgba(0,0,0,0.12);"
                " border-radius:8px; background:white; }"
            )

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _toggle_body(self) -> None:
        self._expanded = not self._expanded
        self._body.setVisible(self._expanded)
        self._chevron.setIcon(
            FluentIcon.CHEVRON_DOWN_MED
            if self._expanded
            else FluentIcon.CHEVRON_RIGHT_MED
        )

    def _on_name_changed(self, text: str) -> None:
        self._name_label.setText(text or "unnamed")
        self._emit_change()

    def _on_default_changed(self, text: str) -> None:
        self._default_label.setText(text)
        self._emit_change()

    def _on_change(self, *_: Any) -> None:
        self._emit_change()

    def _current_mode(self) -> BasicVariableBuildMode:
        return self.mode.__class__(**self.get_values())

    @staticmethod
    def _format_error_message(exc: ValidationError) -> str:
        messages = [error["msg"] for error in exc.errors() if error.get("msg")]
        if messages:
            return "\n".join(messages)
        return str(exc) or "Invalid value."

    def _set_message(self, message: str | None) -> None:
        if message:
            self._message.setText(message)
            self._message.show()
            return
        self._message.clear()
        self._message.hide()

    @staticmethod
    def _parse_list_text(text: str) -> list[Any]:
        stripped = text.strip()
        if not stripped:
            return []

        try:
            parsed = ast.literal_eval(stripped)
        except (SyntaxError, ValueError):
            parsed = None

        if isinstance(parsed, (list, tuple)):
            return list(parsed)

        items: list[Any] = []
        for part in (piece.strip() for piece in text.split(",")):
            if not part:
                continue
            try:
                items.append(ast.literal_eval(part))
            except (SyntaxError, ValueError):
                items.append(part)
        return items

    def _refresh_validation_state(self) -> bool:
        try:
            self.mode = self._current_mode()
        except ValidationError as exc:
            self._set_border(error=True)
            self._set_message(self._format_error_message(exc))
            return False

        self._set_border(error=False)
        self._set_message(None)
        return True

    def _emit_change(self) -> None:
        """Refresh local validation state and notify listeners."""
        self._refresh_validation_state()
        self.changed.emit()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_values(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for fname, widget in self._editors.items():
            annotation = self._mode_fields[fname].annotation
            if isinstance(widget, (SpinBox, DoubleSpinBox)):
                result[fname] = widget.value()
            elif isinstance(widget, SwitchButton):
                result[fname] = widget.isChecked()
            elif isinstance(widget, LineEdit):
                if _is_list_annotation(annotation):
                    result[fname] = self._parse_list_text(widget.text())
                else:
                    result[fname] = widget.text()
        return result

    def get_field_code(self) -> str:
        """Return the current Field() snippet for this card."""
        if not self._refresh_validation_state():
            return ""
        return generate_field_code(self.mode)

    def validate(self) -> bool:
        return self._refresh_validation_state()


if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication

    from chemunited.qt.shared.widgets.base_mode_editor.cards.builder_models import (
        PhysicalQuantitiesMode,
    )

    app = QApplication(sys.argv)
    mode = PhysicalQuantitiesMode()
    card = VariableCard(mode)
    card.show()
    sys.exit(app.exec_())
