from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import FluentIcon, NavigationInterface, NavigationItemPosition


class FrameBase(QFrame):
    """Reusable editor shell with graph, optional workflow, and option panels.

    Layout::

        01 | 02 | 04
        ---|    |
        03 |    |

    01 = graph area
    02 = stacked option panels
    03 = optional workflow area
    04 = fixed navigation rail used to switch option panels
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        graph: QWidget | None = None,
        workflow: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self._graph: QWidget | None = None
        self._workflow: QWidget | None = None
        self._option_pages: dict[str, QWidget] = {}

        self.navigationInterface = NavigationInterface(self, showMenuButton=True)
        self.contentSplitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.graphWorkflowSplitter = QSplitter(Qt.Orientation.Vertical, self)
        self.stackedWidget = QStackedWidget(self)

        self.graphFrame, self._graphLayout = self._build_host_frame()
        self.workflowFrame, self._workflowLayout = self._build_host_frame()
        self.optionsFrame, self._optionsLayout = self._build_host_frame()

        self.initUi()
        self.setGraphWidget(graph)
        self.setWorkflowWidget(workflow)

    def _build_host_frame(self) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame(self)
        frame.setFrameShape(QFrame.NoFrame)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        return frame, layout

    def initUi(self) -> None:
        self.hBoxLayout = QHBoxLayout(self)
        self.hBoxLayout.setContentsMargins(0, 0, 0, 0)
        self.hBoxLayout.setSpacing(0)

        self.graphWorkflowSplitter.addWidget(self.graphFrame)
        self.graphWorkflowSplitter.addWidget(self.workflowFrame)
        self.graphWorkflowSplitter.setStretchFactor(0, 5)
        self.graphWorkflowSplitter.setStretchFactor(1, 2)
        self.graphWorkflowSplitter.setChildrenCollapsible(True)

        self._optionsLayout.addWidget(self.stackedWidget)

        self.contentSplitter.addWidget(self.graphWorkflowSplitter)
        self.contentSplitter.addWidget(self.optionsFrame)
        self.contentSplitter.setStretchFactor(0, 5)
        self.contentSplitter.setStretchFactor(1, 1)
        self.contentSplitter.setChildrenCollapsible(True)

        self.hBoxLayout.addWidget(self.contentSplitter, 1)
        self.hBoxLayout.addWidget(self.navigationInterface)

        self.navigationInterface.setExpandWidth(220)
        self.stackedWidget.currentChanged.connect(self._onCurrentOptionChanged)

        self.workflowFrame.hide()
        self.optionsFrame.hide()

        QTimer.singleShot(0, self.resetSplitterSizes)

    def _clear_layout(self, layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)

    def _set_host_widget(
        self, layout: QVBoxLayout, host: QWidget, widget: QWidget | None
    ) -> None:
        self._clear_layout(layout)
        if widget is None:
            host.hide()
            return

        layout.addWidget(widget)
        host.show()

    def setGraphWidget(self, widget: QWidget | None) -> None:
        self._graph = widget
        self._set_host_widget(self._graphLayout, self.graphFrame, widget)
        QTimer.singleShot(0, self.resetSplitterSizes)

    def setWorkflowWidget(self, widget: QWidget | None) -> None:
        self._workflow = widget
        self._set_host_widget(self._workflowLayout, self.workflowFrame, widget)
        QTimer.singleShot(0, self.resetSplitterSizes)

    def addSubInterface(
        self,
        widget: QWidget,
        icon: Any,
        text: str,
        position: NavigationItemPosition = NavigationItemPosition.TOP,
        routeKey: str | None = None,
        onClick: Callable[[], None] | None = None,
    ) -> None:
        route_key = routeKey or widget.objectName() or text
        widget.setObjectName(route_key)

        self.stackedWidget.addWidget(widget)
        self._option_pages[route_key] = widget
        self.optionsFrame.show()

        def _handle_click() -> None:
            self.switchTo(widget)
            if onClick is not None:
                onClick()

        self.navigationInterface.addItem(
            routeKey=route_key,
            icon=icon,
            text=text,
            onClick=_handle_click,
            position=position,
            tooltip=text,
        )

        if self.stackedWidget.count() == 1:
            self.switchTo(widget)

        QTimer.singleShot(0, self.resetSplitterSizes)

    def addNavigationAction(
        self,
        icon: Any,
        text: str,
        onClick: Callable[[], None],
        position: NavigationItemPosition = NavigationItemPosition.TOP,
        routeKey: str | None = None,
        tooltip: str | None = None,
    ) -> None:
        """Add a navigation item that behaves like a button instead of a page tab."""
        route_key = routeKey or text

        def _handle_click() -> None:
            onClick()
            QTimer.singleShot(0, self._restoreCurrentOptionSelection)

        self.navigationInterface.addItem(
            routeKey=route_key,
            icon=icon,
            text=text,
            onClick=_handle_click,
            position=position,
            tooltip=tooltip or text,
        )

    def switchTo(self, widget_or_key: QWidget | str) -> None:
        if isinstance(widget_or_key, str):
            widget = self._option_pages.get(widget_or_key)
            if widget is None:
                return
        else:
            widget = widget_or_key

        self.stackedWidget.setCurrentWidget(widget)
        self.navigationInterface.setCurrentItem(widget.objectName())

    def resetSplitterSizes(self) -> None:
        total_width = max(self.width(), 600)
        option_width = (
            max(total_width // 6, 220) if self.optionsFrame.isVisible() else 0
        )
        content_width = max(total_width - option_width, 1)
        self.contentSplitter.setSizes([content_width, option_width])

        total_height = max(self.height(), 400)
        if self.workflowFrame.isVisible():
            graph_height = max((total_height * 5) // 7, 1)
            workflow_height = max(total_height - graph_height, 1)
        else:
            graph_height = total_height
            workflow_height = 0

        self.graphWorkflowSplitter.setSizes([graph_height, workflow_height])

    def _restoreCurrentOptionSelection(self) -> None:
        widget = self.stackedWidget.currentWidget()
        if widget is not None:
            self.navigationInterface.setCurrentItem(widget.objectName())

    def _onCurrentOptionChanged(self, index: int) -> None:
        widget = self.stackedWidget.widget(index)
        if widget is not None:
            self.navigationInterface.setCurrentItem(widget.objectName())


if __name__ == "__main__":
    import sys

    def _placeholder(title: str, background: str) -> QLabel:
        label = QLabel(title)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(
            f"""
            QLabel {{
                background: {background};
                border: 1px solid rgba(0, 0, 0, 0.12);
                border-radius: 10px;
                font-size: 16px;
                padding: 24px;
            }}
            """
        )
        return label

    app = QApplication(sys.argv)

    frame = FrameBase(
        graph=_placeholder("Graph Area", "#F5F7FA"),
        workflow=_placeholder("Workflow Area", "#FFF7ED"),
    )
    frame.setWindowTitle("FrameBase Example")
    frame.addSubInterface(
        _placeholder("Inspector Panel", "#EEF2FF"),
        FluentIcon.EDIT,
        "Inspector",
    )
    frame.addSubInterface(
        _placeholder("Layers Panel", "#ECFDF5"),
        FluentIcon.VIEW,
        "Layers",
    )
    frame.addNavigationAction(
        FluentIcon.SAVE,
        "Save",
        onClick=lambda: print("Save clicked"),
        position=NavigationItemPosition.BOTTOM,
    )
    frame.resize(1200, 720)
    frame.show()

    sys.exit(app.exec_())
