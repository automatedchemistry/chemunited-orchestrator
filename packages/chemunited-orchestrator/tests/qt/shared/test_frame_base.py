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
