from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    FluentIcon,
    IndeterminateProgressBar,
    StrongBodyLabel,
    TableWidget,
    TextBrowser,
    TitleLabel,
    TransparentToolButton,
)

from chemunited.qt.pre_run.summary_window import SummaryParametersFrame
from chemunited.qt.shared.icon import OrchestratorIcon
from chemunited.qt.shared.widgets.segment_widget import SegmentWindow

STATE_COLORS = {
    "RUNNING": ("#FFF4E5", "#8D6E00", "#F9A825"),
    "WAITING": ("#EFF6FF", "#1D4ED8", "#3B82F6"),
    "COMPLETED": ("#E8F5E9", "#1B5E20", "#2E7D32"),
    "FINISHED": ("#E8F5E9", "#1B5E20", "#2E7D32"),
    "FAILED": ("#FDECEA", "#B71C1C", "#D32F2F"),
    "ERROR": ("#FDECEA", "#B71C1C", "#D32F2F"),
    "CANCELLED": ("#F3F4F6", "#374151", "#6B7280"),
    "CANCELED": ("#F3F4F6", "#374151", "#6B7280"),
    "STOPPED": ("#F3F4F6", "#374151", "#6B7280"),
    "NOT_VISITED": ("#F3F4F6", "#374151", "#9CA3AF"),
}


def _state_style(state: str) -> tuple[str, str, str]:
    key = state.strip().upper()
    return STATE_COLORS.get(key, ("#F3F4F6", "#111827", "#6B7280"))


def _set_badge_style(label: QLabel, state: str) -> None:
    bg, fg, border = _state_style(state)
    label.setStyleSheet(
        f"""
        QLabel {{
            background: {bg};
            color: {fg};
            border: 1px solid {border};
            border-radius: 5px;
            padding: 4px 8px;
            font-weight: 700;
        }}
        """
    )


def _json_text(value: Any) -> str:
    try:
        return json.dumps(value, indent=2, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


def _compact_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (bool, int, float)):
        return str(value)
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


def _event_label(payload: dict[str, Any]) -> str:
    event_type = payload.get("event_type")
    if event_type:
        return str(event_type)
    if set(payload) == {"state"}:
        return "RUN STATE"
    return "EVENT"


def _format_timestamp(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return ""
    try:
        return datetime.fromtimestamp(value).strftime("%H:%M:%S")
    except (OSError, ValueError):
        return ""


def _format_node_key(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return ":".join(str(part) for part in value)
    if value is None:
        return ""
    return str(value)


def _duration_seconds(runtime: dict[str, Any]) -> str:
    started = runtime.get("started_at")
    finished = runtime.get("finished_at")
    if not isinstance(started, (int, float)) or not isinstance(finished, (int, float)):
        return ""
    return f"{max(0.0, finished - started):.2f} s"


def _process_name_from_protocol_key(key: str) -> str:
    process_name, separator, process_index = key.rpartition("_")
    if separator and process_name and process_index.isdecimal():
        return process_name
    return key


def _display_process_name(key: str) -> str:
    name = _process_name_from_protocol_key(key)
    name = re.sub(r"(?<!^)(?=[A-Z])", " ", name).replace("_", " ")
    return name.strip() or key


class ReportFrame(QWidget):
    def __init__(
        self,
        process_keys: list[str] | None = None,
        parent=None,
    ):
        super().__init__(parent=parent)
        self._process_keys = process_keys or []
        self._run_id: str | None = None
        self._current_process_key: str | None = None
        self._event_count = 0
        self._error_count = 0
        self._init_ui()

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        root.addWidget(self._build_header())

        self.pages = SegmentWindow(self)
        self.stream_page = self._build_stream_page()
        self.report_page = self._build_report_page()
        self.raw_report_browser = TextBrowser(self)
        self.raw_report_browser.setObjectName("raw_report_browser")
        self.raw_report_browser.setReadOnly(True)
        self.raw_report_browser.setPlainText("The final run report will appear here.")

        self.pages.addSubInterface(
            self.stream_page,
            "stream_page",
            "Stream",
            FluentIcon.CHAT.icon(),
        )
        self.pages.addSubInterface(
            self.report_page,
            "report_page",
            "Report",
            FluentIcon.VIEW.icon(),
        )
        self.pages.addSubInterface(
            self.raw_report_browser,
            "raw_report_page",
            "Raw JSON",
            FluentIcon.CODE.icon(),
        )
        root.addWidget(self.pages, 1)
        self._set_state("IDLE")

    def _build_header(self) -> QWidget:
        card = CardWidget(self)
        card.setObjectName("run_header")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)

        title = TitleLabel("Execution Inspector", card)
        self.state_badge = QLabel("IDLE", card)
        self.state_badge.setObjectName("state_badge")
        self.state_badge.setAlignment(Qt.AlignCenter)  # type: ignore[attr-defined]
        self.state_badge.setMinimumWidth(86)

        title_row.addWidget(title)
        title_row.addStretch(1)
        title_row.addWidget(self.state_badge)
        layout.addLayout(title_row)

        meta_row = QHBoxLayout()
        meta_row.setSpacing(16)
        self.run_id_label = CaptionLabel("No active run", card)
        self.run_id_label.setObjectName("run_id_label")
        self.current_process_label = CaptionLabel("Process: --", card)
        self.current_process_label.setObjectName("current_process_label")
        self.event_count_label = CaptionLabel("Events: 0", card)
        self.event_count_label.setObjectName("event_count_label")
        self.error_count_label = CaptionLabel("Errors: 0", card)
        self.error_count_label.setObjectName("error_count_label")
        meta_row.addWidget(self.run_id_label, 1)
        meta_row.addWidget(self.current_process_label)
        meta_row.addWidget(self.event_count_label)
        meta_row.addWidget(self.error_count_label)
        layout.addLayout(meta_row)

        self.progress = IndeterminateProgressBar(card, start=False)
        self.progress.setObjectName("run_progress")
        self.progress.setFixedHeight(4)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)
        return card

    def _build_stream_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.stream_scroll = QScrollArea(page)
        self.stream_scroll.setWidgetResizable(True)
        self.stream_scroll.setFrameShape(QFrame.NoFrame)

        self.stream_content = QWidget(self.stream_scroll)
        self.stream_content.setObjectName("stream_content")
        self.stream_layout = QVBoxLayout(self.stream_content)
        self.stream_layout.setContentsMargins(2, 2, 2, 2)
        self.stream_layout.setSpacing(8)
        self.stream_layout.addStretch(1)

        self.stream_scroll.setWidget(self.stream_content)
        layout.addWidget(self.stream_scroll)
        return page

    def _build_report_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.report_scroll = QScrollArea(page)
        self.report_scroll.setWidgetResizable(True)
        self.report_scroll.setFrameShape(QFrame.NoFrame)

        self.report_content = QWidget(self.report_scroll)
        self.report_content.setObjectName("report_content")
        self.report_layout = QVBoxLayout(self.report_content)
        self.report_layout.setContentsMargins(2, 2, 2, 2)
        self.report_layout.setSpacing(10)
        self._add_report_placeholder("The final report will appear after execution.")

        self.report_scroll.setWidget(self.report_content)
        layout.addWidget(self.report_scroll)
        return page

    def start_run(self, run_id: str) -> None:
        self._run_id = run_id
        self._current_process_key = None
        self._event_count = 0
        self._error_count = 0
        self.run_id_label.setText(f"Run: {run_id}")
        self.current_process_label.setText("Process: --")
        self._update_counts()
        self._set_state("RUNNING")
        self.progress.setVisible(True)
        self.progress.start()
        self._clear_stream()
        self._clear_report()
        self._add_report_placeholder("Waiting for the final execution report.")
        self.raw_report_browser.setPlainText("The final run report will appear here.")
        self.pages.switchTo(self.stream_page)

    def append_stream_event(self, run_id: str, payload: dict[str, Any]) -> None:
        if run_id != self._run_id:
            return
        self._update_current_process(payload)
        if self._should_hide_stream_event(payload):
            return
        self._event_count += 1
        if self._is_error_payload(payload):
            self._error_count += 1
        state = payload.get("state")
        if isinstance(state, str) and set(payload) == {"state"}:
            self._set_state(state.upper())
        self._update_counts()
        self._append_event_row(payload)

    def finish_run(self, state: str) -> None:
        if self._run_id is None:
            return
        self._set_state(state.upper())
        self.progress.pause()
        self.progress.setVisible(False)

    def set_report(self, run_id: str, report: dict[str, Any] | None) -> None:
        if run_id != self._run_id:
            return
        self.progress.pause()
        self.progress.setVisible(False)
        self._clear_report()

        if report is None:
            self._add_report_placeholder("No final report was returned by the API.")
            self.raw_report_browser.setPlainText(
                "No final report was returned by the API."
            )
            self.pages.switchTo(self.report_page)
            return

        state = _compact_value(report.get("state")).upper()
        if state:
            self._set_state(state)
        self._error_count = max(self._error_count, self._count_report_errors(report))
        self._update_counts()
        self.raw_report_browser.setPlainText(_json_text(report))
        self._render_report(report)
        self.pages.switchTo(self.report_page)

    def _set_state(self, state: str) -> None:
        text = state.strip().upper() or "UNKNOWN"
        self.state_badge.setText(text)
        _set_badge_style(self.state_badge, text)

    def _update_current_process(self, payload: dict[str, Any]) -> None:
        process_key = _compact_value(payload.get("process"))
        if not process_key:
            return
        self._current_process_key = process_key
        self.current_process_label.setText(f"Process: {process_key}")

    def _update_counts(self) -> None:
        self.event_count_label.setText(f"Events: {self._event_count}")
        self.error_count_label.setText(f"Errors: {self._error_count}")

    def _clear_stream(self) -> None:
        self._clear_layout(self.stream_layout)
        self.stream_layout.addStretch(1)

    def _clear_report(self) -> None:
        self._clear_layout(self.report_layout)

    @staticmethod
    def _clear_layout(layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()  # type: ignore[attr-defined]
            if widget is not None:
                widget.deleteLater()

    def _add_report_placeholder(self, text: str) -> None:
        label = CaptionLabel(text, self.report_content)
        label.setAlignment(Qt.AlignCenter)  # type: ignore[attr-defined]
        self.report_layout.addWidget(label)
        self.report_layout.addStretch(1)

    def _append_event_row(self, payload: dict[str, Any]) -> None:
        row = self._build_event_row(payload)
        insert_at = max(0, self.stream_layout.count() - 1)
        self.stream_layout.insertWidget(insert_at, row)
        self.stream_scroll.verticalScrollBar().setValue(  # type: ignore[attr-defined]
            self.stream_scroll.verticalScrollBar().maximum()  # type: ignore[attr-defined]
        )

    def _build_event_row(self, payload: dict[str, Any]) -> QWidget:
        card = CardWidget(self.stream_content)
        card.setObjectName("stream_event_row")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(8)

        state_text = _compact_value(payload.get("state")) or _event_label(payload)
        badge = QLabel(_event_label(payload), card)
        badge.setAlignment(Qt.AlignCenter)  # type: ignore[attr-defined]
        _set_badge_style(badge, state_text)

        timestamp = _format_timestamp(payload.get("timestamp"))
        time_label = CaptionLabel(timestamp or "--:--:--", card)
        process_label = CaptionLabel(_compact_value(payload.get("process")), card)
        process_label.setObjectName("event_process_label")
        process_label.setMinimumWidth(90)
        node_label = CaptionLabel(_format_node_key(payload.get("node_key")), card)
        node_label.setObjectName("event_node_label")
        node_label.setMinimumWidth(80)

        raw_button = TransparentToolButton(FluentIcon.CHEVRON_RIGHT_MED, card)
        raw_button.setToolTip("Show raw event JSON")

        header.addWidget(badge)
        header.addWidget(time_label)
        header.addWidget(process_label)
        header.addWidget(node_label)
        header.addStretch(1)
        header.addWidget(raw_button)
        layout.addLayout(header)

        message = BodyLabel(
            _compact_value(payload.get("message")) or "Run state update", card
        )
        message.setObjectName("event_message_label")
        message.setWordWrap(True)
        layout.addWidget(message)

        details_text = self._event_details_text(payload)
        if details_text:
            details = CaptionLabel(details_text, card)
            details.setObjectName("event_details_label")
            details.setWordWrap(True)
            layout.addWidget(details)

        raw = TextBrowser(card)
        raw.setReadOnly(True)
        raw.setPlainText(_json_text(payload))
        raw.setMinimumHeight(120)
        raw.setVisible(False)
        layout.addWidget(raw)

        def toggle_raw() -> None:
            visible = not raw.isVisible()
            raw.setVisible(visible)
            raw_button.setIcon(
                FluentIcon.CHEVRON_DOWN_MED if visible else FluentIcon.CHEVRON_RIGHT_MED
            )

        raw_button.clicked.connect(toggle_raw)  # type: ignore[attr-defined]
        return card

    @staticmethod
    def _event_details_text(payload: dict[str, Any]) -> str:
        details = []
        for key in ("state", "result", "method", "source", "target"):
            value = _compact_value(payload.get(key))
            if value:
                details.append(f"{key}: {value}")
        active = payload.get("active_predecessor_count")
        completed = payload.get("completed_predecessor_count")
        if active is not None or completed is not None:
            details.append(f"predecessors: {completed or 0}/{active or 0}")
        return " | ".join(details)

    @staticmethod
    def _is_error_payload(payload: dict[str, Any]) -> bool:
        event_type = _event_label(payload).upper()
        state = _compact_value(payload.get("state")).upper()
        return (
            "FAILED" in event_type
            or "ERROR" in event_type
            or state in {"FAILED", "ERROR"}
            or bool(payload.get("error"))
        )

    @staticmethod
    def _should_hide_stream_event(payload: dict[str, Any]) -> bool:
        event_type = _event_label(payload).upper()
        state = _compact_value(payload.get("state")).upper()
        return event_type == "NODE_WAITING" or state == "WAITING"

    @staticmethod
    def _count_report_errors(report: dict[str, Any]) -> int:
        results = report.get("results")
        if not isinstance(results, list):
            return 0
        total = 0
        for result in results:
            if isinstance(result, dict) and isinstance(result.get("errors"), dict):
                total += len(result["errors"])
        return total

    def _render_report(self, report: dict[str, Any]) -> None:
        header = CardWidget(self.report_content)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(16, 12, 16, 12)
        header_layout.setSpacing(6)
        header_layout.addWidget(StrongBodyLabel("Run Summary", header))
        header_layout.addWidget(
            BodyLabel(
                f"Run {report.get('run_id', self._run_id) or self._run_id} finished with state "
                f"{_compact_value(report.get('state')) or 'unknown'}.",
                header,
            )
        )
        self.report_layout.addWidget(header)

        results = report.get("results")
        if not isinstance(results, list) or not results:
            self._add_report_placeholder("The report did not contain process results.")
            return

        for index, result in enumerate(results):
            if isinstance(result, dict):
                self.report_layout.addWidget(
                    self._build_process_report_card(index, result)
                )
        self.report_layout.addStretch(1)

    def _build_process_report_card(self, index: int, result: dict[str, Any]) -> QWidget:
        card = CardWidget(self.report_content)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        process_key = _compact_value(result.get("process"))
        process_name = self._process_label(index, process_key)
        state_map = result.get("node_state", {})
        states = list(state_map.values()) if isinstance(state_map, dict) else []
        process_state = (
            "FAILED" if any(str(s).upper() == "FAILED" for s in states) else "COMPLETED"
        )

        title_row = QHBoxLayout()
        title_text = f"Process {index + 1}: {process_name}"
        if process_key and process_key != process_name:
            title_text = f"{title_text} ({process_key})"
        title = StrongBodyLabel(title_text, card)
        badge = QLabel(process_state, card)
        badge.setAlignment(Qt.AlignCenter)  # type: ignore[attr-defined]
        _set_badge_style(badge, process_state)
        title_row.addWidget(title)
        title_row.addStretch(1)
        title_row.addWidget(badge)
        layout.addLayout(title_row)

        errors = result.get("errors")
        if isinstance(errors, dict) and errors:
            layout.addWidget(self._build_errors_card(errors, card))

        table = self._build_nodes_table(result, card)
        layout.addWidget(table)
        return card

    def _build_errors_card(self, errors: dict[str, Any], parent: QWidget) -> QWidget:
        frame = QFrame(parent)
        frame.setObjectName("report_errors_frame")
        frame.setStyleSheet(
            """
            QFrame#report_errors_frame {
                background: #FDECEA;
                border: 1px solid #D32F2F;
                border-radius: 7px;
            }
            """
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)
        layout.addWidget(StrongBodyLabel("Errors", frame))
        for node, error in errors.items():
            label = CaptionLabel(f"{node}: {error}", frame)
            label.setWordWrap(True)
            layout.addWidget(label)
        return frame

    def _build_nodes_table(
        self, result: dict[str, Any], parent: QWidget
    ) -> TableWidget:
        state_map = result.get("node_state", {})
        result_map = result.get("node_result", {})
        runtime_map = result.get("node_runtime", {})
        if not isinstance(state_map, dict):
            state_map = {}
        if not isinstance(result_map, dict):
            result_map = {}
        if not isinstance(runtime_map, dict):
            runtime_map = {}

        table = TableWidget(parent)
        table.setObjectName("report_nodes_table")
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels(
            ["Node", "State", "Result", "Duration", "Status", "Error"]
        )
        table.setRowCount(len(state_map))
        table.setAlternatingRowColors(True)
        table.setWordWrap(True)
        table.verticalHeader().setVisible(False)  # type: ignore[attr-defined]
        table.setEditTriggers(TableWidget.NoEditTriggers)  # type: ignore[attr-defined]
        table.setSelectionBehavior(TableWidget.SelectRows)  # type: ignore[attr-defined]
        table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)

        for row, (node, state) in enumerate(state_map.items()):
            runtime = runtime_map.get(node)
            runtime = runtime if isinstance(runtime, dict) else {}
            values = [
                node,
                _compact_value(state),
                _compact_value(result_map.get(node)),
                _duration_seconds(runtime),
                _compact_value(runtime.get("status_message")),
                _compact_value(runtime.get("error")),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                table.setItem(row, col, item)

        table.resizeColumnsToContents()
        table.resizeRowsToContents()
        table.setMinimumHeight(min(420, 92 + max(1, len(state_map)) * 36))
        return table

    def _process_label(self, index: int, process_key: str = "") -> str:
        if process_key:
            return _display_process_name(process_key)
        if 0 <= index < len(self._process_keys):
            return _display_process_name(self._process_keys[index])
        return f"Process {index + 1}"


class SummaryExecutionWindow(SegmentWindow):
    def __init__(self, data: dict[str, Any], file_path: Path, parent=None):
        super().__init__(parent=parent)
        self._file_path = file_path
        self._data = data
        self.summary_frame = SummaryParametersFrame(file_path, data, self)
        self.report_frame = ReportFrame(self._process_keys(data), self)
        self.initUI()
        self.setWindowTitle(f"Execution summary - {file_path.name}")
        self.resize(920, 680)

    def initUI(self):
        self.addSubInterface(
            widget=self.summary_frame,
            objectName="summary_frame",
            text="Parameters",
            icon=OrchestratorIcon.VARIABLE.icon(),
        )

        self.addSubInterface(
            widget=self.report_frame,
            objectName="report_frame",
            text="Report",
            icon=OrchestratorIcon.STATUS.icon(),
        )

    def start_run(self, run_id: str) -> None:
        self.report_frame.start_run(run_id)
        self.switchTo(self.report_frame)

    def append_stream_event(self, run_id: str, payload: dict[str, Any]) -> None:
        self.report_frame.append_stream_event(run_id, payload)

    def set_report(self, run_id: str, report: dict[str, Any] | None) -> None:
        self.report_frame.set_report(run_id, report)
        self.switchTo(self.report_frame)

    def finish_run(self, state: str) -> None:
        self.report_frame.finish_run(state)

    @staticmethod
    def _process_keys(data: dict[str, Any]) -> list[str]:
        return [key for key in data if key != "main_parameter"]

    @classmethod
    def inspect_file(cls, file_path: Path) -> "SummaryExecutionWindow | None":
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

        if not isinstance(data, dict):
            return None
        if any(not isinstance(value, dict) for value in data.values()):
            return None
        return cls(data=data, file_path=file_path)
