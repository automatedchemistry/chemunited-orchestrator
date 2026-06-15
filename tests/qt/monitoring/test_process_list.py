from __future__ import annotations

from chemunited_workflow.enums import NodeState
from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import QWidget
from pytestqt.qtbot import QtBot

from chemunited.monitoring.process_list import MonitorProcessesWidget


class DummyOrchestrator(QObject):
    protocol_execution_started = pyqtSignal(str)
    protocol_execution_finished = pyqtSignal(str)
    process_status_changed = pyqtSignal(str, object)

    def __init__(self) -> None:
        super().__init__()
        self.protocols = {}
        self.execute_result = True
        self.stop_result = True
        self.selected: list[str] = []

    def select_process(self, name: str) -> None:
        self.selected.append(name)

    def execute(self) -> bool:
        return self.execute_result

    def stop_execution(self) -> bool:
        return self.stop_result


class DummyMonitor(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.orchestrator = DummyOrchestrator()


def test_monitor_processes_widget_has_stop_above_execute(qtbot: QtBot) -> None:
    parent = DummyMonitor()
    qtbot.addWidget(parent)
    widget = MonitorProcessesWidget(parent)
    qtbot.addWidget(widget)

    assert widget.stop_btn.text() == "Stop Protocol"
    assert widget.execute_btn.text() == "Execute"
    assert widget.stop_btn.isEnabled()
    assert widget.execute_btn.isEnabled()


def test_monitor_processes_widget_toggles_buttons_while_running(
    qtbot: QtBot,
) -> None:
    parent = DummyMonitor()
    qtbot.addWidget(parent)
    widget = MonitorProcessesWidget(parent)
    qtbot.addWidget(widget)

    widget._execute_protocol()

    assert not widget.execute_btn.isEnabled()
    assert widget.stop_btn.isEnabled()

    parent.orchestrator.protocol_execution_finished.emit("completed")

    assert widget.execute_btn.isEnabled()
    assert widget.stop_btn.isEnabled()


def test_monitor_processes_widget_stop_button_resets_state(qtbot: QtBot) -> None:
    parent = DummyMonitor()
    qtbot.addWidget(parent)
    widget = MonitorProcessesWidget(parent)
    qtbot.addWidget(widget)
    widget._set_execution_running(True)

    widget._stop_protocol()

    assert widget.execute_btn.isEnabled()
    assert widget.stop_btn.isEnabled()


def test_monitor_processes_widget_updates_status_by_active_key(qtbot: QtBot) -> None:
    parent = DummyMonitor()
    qtbot.addWidget(parent)
    widget = MonitorProcessesWidget(parent)
    qtbot.addWidget(widget)

    widget.set_active_processes([("Mixing_0", "Mixing"), ("Mixing_1", "Mixing")])

    first = widget.active_list.process_item("Mixing_0")
    second = widget.active_list.process_item("Mixing_1")
    assert first is not None
    assert second is not None

    parent.orchestrator.process_status_changed.emit("Mixing_1", NodeState.RUNNING)

    assert first._status._state == NodeState.NOT_VISITED
    assert second._status._state == NodeState.RUNNING
