from __future__ import annotations

from chemunited_workflow.enums import NodeState

from chemunited.qt.protocols.workflows.elements.status_bar import (
    _STATUS_COMPLETED_COLOR,
    _STATUS_FAILED_COLOR,
    _STATUS_RUNNING_COLOR,
    _STATUS_WAITING_COLOR,
    WorkflowStatusBar,
)


def test_workflow_status_bar_hides_for_inactive_states(qtbot) -> None:
    bar = WorkflowStatusBar(120)
    qtbot.addWidget(bar)

    for state in (NodeState.NOT_VISITED, NodeState.INACTIVE, None):
        visible = bar.set_status(state)

        assert visible is False
        assert bar.is_running() is False
        assert bar.value() == 0


def test_workflow_status_bar_waiting_is_static_yellow(qtbot) -> None:
    bar = WorkflowStatusBar(120)
    qtbot.addWidget(bar)

    visible = bar.set_status(NodeState.WAITING)

    assert visible is True
    assert bar._state == NodeState.WAITING
    assert bar.value() == 100
    assert bar.bar_color() == _STATUS_WAITING_COLOR
    assert bar.is_running() is False


def test_workflow_status_bar_running_is_green_and_animated(qtbot) -> None:
    bar = WorkflowStatusBar(120)
    qtbot.addWidget(bar)

    visible = bar.set_status(NodeState.RUNNING)

    assert visible is True
    assert bar._state == NodeState.RUNNING
    assert bar.value() == 100
    assert bar.bar_color() == _STATUS_RUNNING_COLOR
    assert bar.is_running() is True


def test_workflow_status_bar_completed_and_failed_freeze_at_full(qtbot) -> None:
    bar = WorkflowStatusBar(120)
    qtbot.addWidget(bar)

    assert bar.set_status(NodeState.COMPLETED) is True
    assert bar.value() == 100
    assert bar.bar_color() == _STATUS_COMPLETED_COLOR
    assert bar.is_running() is False

    assert bar.set_status("NodeState.FAILED") is True
    assert bar._state == NodeState.FAILED
    assert bar.value() == 100
    assert bar.bar_color() == _STATUS_FAILED_COLOR


def test_workflow_status_bar_coerces_plain_state_name(qtbot) -> None:
    bar = WorkflowStatusBar(120)
    qtbot.addWidget(bar)

    assert bar.set_status("FAILED") is True
    assert bar._state == NodeState.FAILED
