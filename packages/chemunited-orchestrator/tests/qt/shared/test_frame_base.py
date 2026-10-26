from PyQt5.QtWidgets import QLabel
from pytestqt.qtbot import QtBot
from qfluentwidgets import FluentIcon

from chemunited.shared.widgets.frame_base import FrameBase


def test_switch_to_reopens_collapsed_option_pane(qtbot: QtBot):
    frame = FrameBase(graph=QLabel("Graph"))
    first = QLabel("First panel")
    second = QLabel("Second panel")
    qtbot.addWidget(frame)

    frame.addSubInterface(first, FluentIcon.EDIT, "First")
    frame.addSubInterface(second, FluentIcon.VIEW, "Second")
    frame.resize(1200, 720)
    frame.show()
    qtbot.waitExposed(frame)
    qtbot.waitUntil(lambda: frame.contentSplitter.sizes()[1] > 0, timeout=1000)

    frame.switchTo(second)
    qtbot.wait(0)
    frame.contentSplitter.setSizes([frame.width(), 0])
    qtbot.waitUntil(lambda: frame.contentSplitter.sizes()[1] <= 1, timeout=1000)

    frame.switchTo(second)

    qtbot.waitUntil(lambda: frame.contentSplitter.sizes()[1] > 0, timeout=1000)


def test_panes_laid_out_while_hidden_open_once_shown(qtbot: QtBot):
    frame = FrameBase(graph=QLabel("Graph"), workflow=QLabel("Workflow"))
    qtbot.addWidget(frame)
    frame.addSubInterface(QLabel("Panel"), FluentIcon.EDIT, "Panel")
    # The deferred size resets run while the frame is still off screen, like a
    # window built at start-up and shown later.
    qtbot.wait(10)

    frame.resize(1200, 720)
    frame.show()
    qtbot.waitExposed(frame)

    qtbot.waitUntil(lambda: frame.graphWorkflowSplitter.sizes()[1] > 0, timeout=1000)
    qtbot.waitUntil(lambda: frame.contentSplitter.sizes()[1] > 0, timeout=1000)
    # Sized against the real width, not the off-screen fallback.
    assert frame.contentSplitter.sizes()[1] < frame.width() // 3


def test_pane_collapsed_by_user_stays_collapsed_when_shown_again(qtbot: QtBot):
    frame = FrameBase(graph=QLabel("Graph"), workflow=QLabel("Workflow"))
    qtbot.addWidget(frame)
    frame.resize(1200, 720)
    frame.show()
    qtbot.waitExposed(frame)
    qtbot.waitUntil(lambda: frame.graphWorkflowSplitter.sizes()[1] > 0, timeout=1000)
    qtbot.wait(10)  # let every deferred reset from construction run first

    frame.graphWorkflowSplitter.setSizes([frame.height(), 0])
    qtbot.waitUntil(lambda: frame.graphWorkflowSplitter.sizes()[1] <= 1, timeout=1000)
    frame.hide()
    frame.show()
    qtbot.waitExposed(frame)
    qtbot.wait(10)

    assert frame.graphWorkflowSplitter.sizes()[1] <= 1
