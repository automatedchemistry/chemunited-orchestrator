from typing import Any

from PyQt5.QtWidgets import QStackedWidget, QVBoxLayout, QWidget
from qfluentwidgets import SegmentedWidget


class SegmentWindow(QWidget):

    def __init__(self, parent):
        super().__init__(parent)

        self.pivot = SegmentedWidget(self)
        self.stackedWidget = QStackedWidget(self)
        self.vBoxLayout = QVBoxLayout(self)

        self.vBoxLayout.addWidget(self.pivot)
        self.vBoxLayout.addWidget(self.stackedWidget)
        self.vBoxLayout.setContentsMargins(10, 10, 10, 10)

        self.pivot.currentItemChanged.connect(
            lambda k: self.switchTo(self.findChild(QWidget, k))
        )

    def addSubInterface(
        self, widget: QWidget, objectName: str, text, icon: str, onClick: Any = None
    ):
        widget.setObjectName(objectName)
        self.stackedWidget.addWidget(widget)
        self.pivot.addItem(routeKey=objectName, text=text, icon=icon, onClick=onClick)

    def switchTo(self, widget):
        self.stackedWidget.setCurrentWidget(widget)
