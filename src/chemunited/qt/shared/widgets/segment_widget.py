from typing import Any

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QStackedWidget, QVBoxLayout, QWidget
from qfluentwidgets import SegmentedWidget


class SegmentWindow(QWidget):
    current_widget_changed = pyqtSignal(str)

    def __init__(self, parent):
        super().__init__(parent)

        self.pivot = SegmentedWidget(self)
        self.stackedWidget = QStackedWidget(self)
        self.vBoxLayout = QVBoxLayout(self)

        self.vBoxLayout.addWidget(self.pivot)
        self.vBoxLayout.addWidget(self.stackedWidget)
        self.vBoxLayout.setContentsMargins(10, 10, 10, 10)

        self.pivot.currentItemChanged.connect(self._switch_to_route_key)
        self.stackedWidget.currentChanged.connect(self._emit_current_widget_name)

    def addSubInterface(
        self, widget: QWidget, objectName: str, text, icon: str, onClick: Any = None
    ):
        widget.setObjectName(objectName)
        self.stackedWidget.addWidget(widget)
        self.pivot.addItem(routeKey=objectName, text=text, icon=icon, onClick=onClick)

    def switchTo(self, widget):
        if widget is None:
            return
        self.stackedWidget.setCurrentWidget(widget)

    def _switch_to_route_key(self, route_key: str) -> None:
        self.switchTo(self.findChild(QWidget, route_key))

    def _emit_current_widget_name(self, index: int) -> None:
        widget = self.stackedWidget.widget(index)
        if widget is not None:
            self.current_widget_changed.emit(widget.objectName())
