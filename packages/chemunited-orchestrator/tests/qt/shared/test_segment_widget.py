from PyQt5.QtWidgets import QWidget
from pytestqt.qtbot import QtBot
from qfluentwidgets import FluentIcon

from chemunited.shared.widgets.segment_widget import SegmentWindow


def test_segment_window_emits_widget_name_when_switching(qtbot: QtBot):
    window = SegmentWindow(None)
    first = QWidget()
    second = QWidget()
    qtbot.addWidget(window)

    window.addSubInterface(first, "first_page", "First", FluentIcon.EDIT)
    window.addSubInterface(second, "second_page", "Second", FluentIcon.VIEW)

    with qtbot.waitSignal(window.current_widget_changed, timeout=1000) as signal:
        window.switchTo(second)

    assert signal.args == ["second_page"]
