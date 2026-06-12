from typing import override

from PyQt5.QtCore import QFile, Qt, QTextStream, QTimer
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication, QHBoxLayout, QStackedWidget, QWidget

_ICON_PATH = ":/icons/icons/chemunited.ico"

from qfluentwidgets import (
    FluentIcon,
    NavigationInterface,
    NavigationItemPosition,
    isDarkTheme,
    qrouter,
)
from qframelesswindow import FramelessWindow, StandardTitleBar

from chemunited.qt.shared.enums import WindowCategory
from chemunited.qt.shared.widgets.loggings_widget import FrameLoggings


class WindowBase(FramelessWindow):
    QSS_FILE: str = ""
    TITLE: str = ""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setTitleBar(StandardTitleBar(self))

        self.hBoxLayout = QHBoxLayout(self)
        self.navigationInterface = NavigationInterface(self, showMenuButton=True)
        self.stackWidget = QStackedWidget(self)

    def buildUi(self):
        """Build the UI"""
        # initialize layout
        self.initLayout()

        # add items to navigation interface
        self.initNavigation()

        self.initWindow()

        self.setTheme()

    def initLayout(self):
        """Initialize the layout"""
        self.hBoxLayout.setSpacing(0)
        self.hBoxLayout.setContentsMargins(0, self.titleBar.height(), 0, 0)
        self.hBoxLayout.addWidget(self.navigationInterface)
        self.hBoxLayout.addWidget(self.stackWidget)
        self.hBoxLayout.setStretchFactor(self.stackWidget, 1)

        self.titleBar.raise_()
        self.navigationInterface.displayModeChanged.connect(self.titleBar.raise_)  # type: ignore[attr-defined]

    def initNavigation(self):
        """Initialize the navigation interface"""
        # enable acrylic effect
        # self.navigationInterface.setAcrylicEnabled(True)

        # set the maximum width
        self.navigationInterface.setExpandWidth(300)

        self.stackWidget.currentChanged.connect(self.onCurrentInterfaceChanged)  # type: ignore[attr-defined]
        self.stackWidget.setCurrentIndex(0)

    def initWindow(self):
        """Initialize the window"""
        self.setWindowIcon(QIcon(_ICON_PATH))
        self.setWindowTitle(self.TITLE)
        self.titleBar.setAttribute(Qt.WA_StyledBackground)  # type: ignore[attr-defined]

    def showEvent(self, event):
        super().showEvent(event)
        self.titleBar.iconLabel.setPixmap(QIcon(_ICON_PATH).pixmap(20, 20))

    def addSubInterface(
        self, interface, icon, text: str, position=NavigationItemPosition.TOP
    ):
        """Add a top-level page to the main window navigation."""
        route_key = interface.objectName() or text
        interface.setObjectName(route_key)

        self.stackWidget.addWidget(interface)
        self.navigationInterface.addItem(
            routeKey=route_key,
            icon=icon,
            text=text,
            onClick=lambda: self.switchTo(interface),
            position=position,
            tooltip=text,
        )

    def setQss(self):
        """Set the QSS"""
        color = "dark" if isDarkTheme() else "light"
        path = f":/styles/qss/{color}/{self.QSS_FILE}"

        file = QFile(path)
        if file.open(QFile.ReadOnly | QFile.Text):  # type: ignore[attr-defined]
            stream = QTextStream(file)
            qss = stream.readAll()
            self.setStyleSheet(qss)
            file.close()
        else:
            print(f"Failed to open QSS file: {path}")

    def switchTo(self, widget):
        """Switch to the given widget"""
        self.stackWidget.setCurrentWidget(widget)

    def onCurrentInterfaceChanged(self, index):
        """Handle current interface changed"""
        widget = self.stackWidget.widget(index)
        if widget:
            self.navigationInterface.setCurrentItem(widget.objectName())
            qrouter.push(self.stackWidget, widget.objectName())

    def resizeEvent(self, e):
        """Handle resize event"""
        super().resizeEvent(e)
        self.titleBar.move(46, 0)
        self.titleBar.resize(self.width() - 46, self.titleBar.height())
        self.titleBar.raise_()

    def setTheme(self):
        """Handle theme change"""
        self.setQss()


class MainWindowBase(WindowBase):
    TITLE: str = "Chemunited Orchestration Software"
    WINDOW_TYPE: WindowCategory = WindowCategory.SETUP
    QSS_FILE: str = "main_window.qss"

    def __init__(self):
        super().__init__()
        # Timer to drain bus in the GUI thread safely
        self.drain_bus_timer = QTimer(self)

    @override
    def initLayout(self):
        """Initialize the layout"""
        super().initLayout()
        # Frames
        self.FrameLoggings = FrameLoggings(self)

    @override
    def initNavigation(self):
        """Initialize the navigation interface"""
        super().initNavigation()

        self.addSubInterface(
            self.FrameLoggings,
            FluentIcon.MESSAGE,
            "Loggings Console",
            NavigationItemPosition.BOTTOM,
        )

    @override
    def initWindow(self):
        """Initialize the window"""
        super().initWindow()
        self.resize(900, 700)
        desktop = QApplication.desktop().availableGeometry()  # type: ignore[union-attr]
        w, h = desktop.width(), desktop.height()
        self.move(w // 2 - self.width() // 2, h // 2 - self.height() // 2)


if __name__ == "__main__":
    import sys

    app = QApplication(sys.argv)
    window = MainWindowBase()
    window.buildUi()
    window.show()
    sys.exit(app.exec_())
