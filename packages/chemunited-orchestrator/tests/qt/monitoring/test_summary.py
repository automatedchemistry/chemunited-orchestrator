from __future__ import annotations

from PyQt5.QtWidgets import QLabel
from pytestqt.qtbot import QtBot
from qfluentwidgets import TableWidget

from chemunited.monitoring.summary import ReportFrame


def _label_texts(widget) -> list[str]:
    return [label.text() for label in widget.findChildren(QLabel)]


def test_report_frame_start_run_and_stream_events(qtbot: QtBot) -> None:
    frame = ReportFrame(["Mixing_0"])
    qtbot.addWidget(frame)

    frame.start_run("RUN-1")
    frame.append_stream_event(
        "RUN-1",
        {
            "event_type": "NODE_WAITING",
            "message": "Waiting hidden",
            "process": "Mixing_0",
            "node_key": ["script_1", 0],
            "state": "WAITING",
        },
    )
    frame.append_stream_event(
        "RUN-1",
        {
            "event_type": "NODE_FAILED",
            "message": "Pump failed",
            "process": "Mixing_0",
            "node_key": ["script_1", 0],
            "state": "FAILED",
            "timestamp": 1780308444.717622,
        },
    )
    frame.append_stream_event(
        "STALE",
        {"event_type": "NODE_RUNNING", "message": "Should be ignored"},
    )

    texts = _label_texts(frame)
    assert frame.state_badge.text() == "RUNNING"
    assert frame.run_id_label.text() == "Run: RUN-1"
    assert frame.current_process_label.text() == "Process: Mixing_0"
    assert frame.event_count_label.text() == "Events: 1"
    assert frame.error_count_label.text() == "Errors: 1"
    assert "NODE_FAILED" in texts
    assert "Mixing_0" in texts
    assert "script_1:0" in texts
    assert "Pump failed" in texts
    assert "NODE_WAITING" not in texts
    assert "Waiting hidden" not in texts
    assert "Should be ignored" not in texts


def test_report_frame_renders_final_report_and_raw_json(qtbot: QtBot) -> None:
    report = {
        "run_id": "RUN-1",
        "state": "finished",
        "results": [
            {
                "process": "Mixing_0",
                "node_state": {
                    "start:0": "COMPLETED",
                    "script_1:0": "FAILED",
                },
                "node_result": {
                    "start:0": True,
                    "script_1:0": None,
                },
                "node_runtime": {
                    "start:0": {
                        "status_message": "Node completed with result True.",
                        "result": True,
                        "error": None,
                        "started_at": 10.0,
                        "finished_at": 11.5,
                        "local_data": {},
                    },
                    "script_1:0": {
                        "status_message": "Node execution failed: timeout",
                        "result": None,
                        "error": "timeout",
                        "started_at": 12.0,
                        "finished_at": 15.25,
                        "local_data": {},
                    },
                },
                "errors": {"script_1:0": "timeout"},
            }
        ],
    }
    frame = ReportFrame(["Mixing_0"])
    qtbot.addWidget(frame)

    frame.start_run("RUN-1")
    frame.set_report("RUN-1", report)
    frame.set_report("STALE", {"run_id": "STALE", "state": "failed"})

    texts = _label_texts(frame)
    raw = frame.raw_report_browser
    tables = frame.findChildren(TableWidget)

    assert frame.state_badge.text() == "FINISHED"
    assert frame.error_count_label.text() == "Errors: 1"
    assert "Process 1: Mixing (Mixing_0)" in texts
    assert "FAILED" in texts
    assert "Errors" in texts
    assert "script_1:0: timeout" in texts
    assert '"run_id": "RUN-1"' in raw.toPlainText()
    assert '"run_id": "STALE"' not in raw.toPlainText()
    assert len(tables) == 1
    assert tables[0].rowCount() == 2
    assert tables[0].item(1, 0).text() == "script_1:0"
    assert tables[0].item(1, 1).text() == "FAILED"
    assert tables[0].item(1, 3).text() == "3.25 s"
