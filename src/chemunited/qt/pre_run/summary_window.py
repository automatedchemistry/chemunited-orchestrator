from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import BodyLabel, CaptionLabel, StrongBodyLabel, TitleLabel


class SummaryWindow(QMainWindow):
    """Read-only summary for a saved pre-run JSON protocol script."""

    def __init__(self, file_path: Path, data: dict[str, Any], parent=None):
        super().__init__(parent=parent)
        self._file_path = file_path
        self._data = data

        self.setWindowTitle(f"Protocol summary - {file_path.name}")
        self.resize(760, 620)
        self._init_ui()

    @classmethod
    def inspect_file(cls, file_path: Path) -> "SummaryWindow | None":
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

        if not isinstance(data, dict):
            return None
        if any(not isinstance(value, dict) for value in data.values()):
            return None
        return cls(file_path, data)

    def _init_ui(self) -> None:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        content = QWidget(scroll)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        layout.addWidget(self._build_header(content))

        if not self._data:
            empty = CaptionLabel("This protocol script does not contain parameters.")
            empty.setAlignment(Qt.AlignCenter)  # type: ignore[attr-defined]
            layout.addWidget(empty)
        else:
            for key, parameters in self._ordered_sections():
                layout.addWidget(self._build_section(key, parameters, content))

        layout.addStretch(1)
        scroll.setWidget(content)
        self.setCentralWidget(scroll)

    def _build_header(self, parent: QWidget) -> QWidget:
        header = QWidget(parent)
        layout = QVBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 4)
        layout.setSpacing(4)

        title = TitleLabel(self._file_path.stem, header)
        path = CaptionLabel(str(self._file_path), header)
        path.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(path)
        return header

    def _build_section(
        self,
        key: str,
        parameters: dict[str, Any],
        parent: QWidget,
    ) -> QWidget:
        section = QFrame(parent)
        section.setObjectName("summarySection")
        section.setStyleSheet(
            """
            QFrame#summarySection {
                background: palette(base);
                border: 1px solid rgba(0, 0, 0, 28);
                border-radius: 8px;
            }
            """
        )

        layout = QVBoxLayout(section)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        title = StrongBodyLabel(self._section_title(key), section)
        layout.addWidget(title)

        if not parameters:
            empty = CaptionLabel("No parameters saved.", section)
            layout.addWidget(empty)
            return section

        for name, value in parameters.items():
            layout.addWidget(self._build_parameter_row(name, value, section))

        return section

    def _build_parameter_row(self, name: str, value: Any, parent: QWidget) -> QWidget:
        row = QFrame(parent)
        row.setObjectName("parameterRow")
        row.setMinimumHeight(44)
        row.setStyleSheet(
            """
            QFrame#parameterRow {
                background: rgba(0, 0, 0, 5);
                border: 1px solid rgba(0, 0, 0, 20);
                border-radius: 7px;
            }
            QFrame#parameterRow:hover {
                background: rgba(0, 120, 212, 12);
                border-color: rgba(0, 120, 212, 70);
            }
            """
        )

        layout = QHBoxLayout(row)
        layout.setContentsMargins(12, 7, 12, 7)
        layout.setSpacing(10)

        handle = CaptionLabel("::", row)
        handle.setFixedWidth(18)
        handle.setAlignment(Qt.AlignCenter)  # type: ignore[attr-defined]

        badge = QLabel(self._type_name(value), row)
        badge.setObjectName("typeBadge")
        badge.setAlignment(Qt.AlignCenter)  # type: ignore[attr-defined]
        badge.setFixedWidth(48)
        badge.setStyleSheet(
            """
            QLabel#typeBadge {
                background: #E7F1FF;
                color: #005FB8;
                border-radius: 4px;
                font-weight: 700;
                padding: 3px 6px;
            }
            """
        )

        name_label = BodyLabel(name, row)
        name_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        value_label = CaptionLabel(self._format_value(value), row)
        value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)  # type: ignore[attr-defined]
        value_label.setWordWrap(True)
        value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)  # type: ignore[attr-defined]
        value_label.setMinimumWidth(180)
        value_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        layout.addWidget(handle)
        layout.addWidget(badge)
        layout.addWidget(name_label, stretch=2)
        layout.addWidget(value_label, stretch=3)
        return row

    def _ordered_sections(self) -> list[tuple[str, dict[str, Any]]]:
        main = [
            (key, value) for key, value in self._data.items() if key == "main_parameter"
        ]
        processes = [
            (key, value) for key, value in self._data.items() if key != "main_parameter"
        ]
        return main + processes

    @staticmethod
    def _section_title(key: str) -> str:
        if key == "main_parameter":
            return "Main Parameters"

        match = re.fullmatch(r"(.+?)(?:_parameters)?_(\d+)", key)
        if match:
            class_name, index = match.groups()
            spaced = re.sub(r"(?<!^)(?=[A-Z])", " ", class_name).replace(" Process", "")
            return f"{spaced} Parameters #{int(index) + 1}"
        return key.replace("_", " ").title()

    @staticmethod
    def _type_name(value: Any) -> str:
        if isinstance(value, bool):
            return "BOOL"
        if isinstance(value, int):
            return "INT"
        if isinstance(value, float):
            return "FLOAT"
        if isinstance(value, str):
            return "STR"
        if isinstance(value, list):
            return "LIST"
        if isinstance(value, dict):
            return "DICT"
        if value is None:
            return "NONE"
        return type(value).__name__.upper()[:5]

    @staticmethod
    def _format_value(value: Any) -> str:
        if isinstance(value, str):
            return value
        if value is None:
            return "None"
        if isinstance(value, (bool, int, float)):
            return str(value)
        return json.dumps(value, ensure_ascii=False)
