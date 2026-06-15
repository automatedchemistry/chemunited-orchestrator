from __future__ import annotations

from chemunited_workflow.enums import NodeState

from chemunited.shared.prcess_list.item import (
    _STATUS_COMPLETED_COLOR,
    _STATUS_DEFAULT_COLOR,
    _STATUS_FAILED_COLOR,
    _STATUS_RUNNING_COLOR,
    ProcessItem,
)


def test_process_item_static_node_states_keep_default_status_color(qtbot) -> None:
    item = ProcessItem("Mixing")
    qtbot.addWidget(item)

    for state in (NodeState.NOT_VISITED, NodeState.WAITING, NodeState.INACTIVE):
        item.set_status(state)

        assert item._status._state == state
        assert item._status._color == _STATUS_DEFAULT_COLOR
        assert not item._status._blink_timer.isActive()


def test_process_item_running_status_blinks_green(qtbot) -> None:
    item = ProcessItem("Mixing")
    qtbot.addWidget(item)

    item.set_status(NodeState.RUNNING)
    first_color = item._status._color
    item._status._toggle_running_blink()

    assert item._status._state == NodeState.RUNNING
    assert item._status._blink_timer.isActive()
    assert first_color == _STATUS_RUNNING_COLOR
    assert item._status._color != first_color


def test_process_item_completed_and_failed_status_colors(qtbot) -> None:
    item = ProcessItem("Mixing")
    qtbot.addWidget(item)

    item.set_status(NodeState.COMPLETED)
    assert item._status._color == _STATUS_COMPLETED_COLOR
    assert not item._status._blink_timer.isActive()

    item.set_status("NodeState.FAILED")
    assert item._status._state == NodeState.FAILED
    assert item._status._color == _STATUS_FAILED_COLOR
    assert not item._status._blink_timer.isActive()
