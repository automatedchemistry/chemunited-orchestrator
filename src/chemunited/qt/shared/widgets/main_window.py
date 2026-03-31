from PyQt5.QtCore import QFile, Qt, QTextStream, QTimer
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication, QHBoxLayout, QStackedWidget
from qfluentwidgets import (
    FluentIcon,
    NavigationInterface,
    NavigationItemPosition,
    isDarkTheme,
    qrouter,
)
from qframelesswindow import FramelessWindow, StandardTitleBar

from chemunited.shared.enums import WindowCategory
from chemunited.shared.icon import OrchestratorIcon
from chemunited.shared.widgets.loggings_widget import FrameLoggings


class MainWindowBase(FramelessWindow):
    TITLE: str = "Chemunited Orchestration Software"
    WINDOW_TYPE: WindowCategory = WindowCategory.SETUP

    def __init__(self):
        super().__init__()
        self.setTitleBar(StandardTitleBar(self))

        self.hBoxLayout = QHBoxLayout(self)
        self.navigationInterface = NavigationInterface(self, showMenuButton=True)
        self.stackWidget = QStackedWidget(self)

        """ Error handle Qtimer """

        # Timer to drain bus in the GUI thread safely
        self.drain_bus_timer = QTimer(self)

    def buildUi(self):
        """Build the UI"""
        # initialize layout
        self.initLayout()

        # add items to navigation interface
        self.initNavigation()

        self.initWindow()

    def initLayout(self):
        """Initialize the layout"""
        self.hBoxLayout.setSpacing(0)
        self.hBoxLayout.setContentsMargins(0, self.titleBar.height(), 0, 0)
        self.hBoxLayout.addWidget(self.navigationInterface)
        self.hBoxLayout.addWidget(self.stackWidget)
        self.hBoxLayout.setStretchFactor(self.stackWidget, 1)

        # Frames
        self.FrameLoggings = FrameLoggings(self)

        self.titleBar.raise_()
        self.navigationInterface.displayModeChanged.connect(self.titleBar.raise_)

    def initNavigation(self):
        """Initialize the navigation interface"""
        # enable acrylic effect
        # self.navigationInterface.setAcrylicEnabled(True)

        self.addSubInterface(
            self.FrameLoggings,
            FluentIcon.MESSAGE,
            "Loggings Console",
            NavigationItemPosition.BOTTOM,
        )

        # set the maximum width
        self.navigationInterface.setExpandWidth(300)

        self.stackWidget.currentChanged.connect(self.onCurrentInterfaceChanged)
        self.stackWidget.setCurrentIndex(0)

    def initWindow(self):
        """Initialize the window"""
        self.resize(900, 700)
        self.setWindowIcon(QIcon(OrchestratorIcon.CHEMUNITED.path()))
        self.setWindowTitle(self.TITLE)
        self.titleBar.setAttribute(Qt.WA_StyledBackground)  # type: ignore[attr-defined]

        desktop = QApplication.desktop().availableGeometry()  # type: ignore[union-attr]
        w, h = desktop.width(), desktop.height()
        self.move(w // 2 - self.width() // 2, h // 2 - self.height() // 2)
        self.setTheme()

    def addSubInterface(
        self, interface, icon, text: str, position=NavigationItemPosition.TOP
    ):
        """add sub interface"""
        self.stackWidget.addWidget(interface)
        self.navigationInterface.addItem(
            routeKey=text,
            icon=icon,
            text=text,
            onClick=lambda: self.switchTo(interface),
            position=position,
            tooltip=text,
        )

    def setQss(self):
        """Set the QSS"""
        color = "dark" if isDarkTheme() else "light"
        path = f":/styles/qss/{color}/main_window.qss"

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
        self.titleBar.move(46, 0)
        self.titleBar.resize(self.width() - 46, self.titleBar.height())

    def setTheme(self):
        """Handle theme change"""
        self.setQss()


if __name__ == "__main__":
    import sys

    app = QApplication(sys.argv)
    window = MainWindowBase()
    window.buildUi()
    window.show()
    sys.exit(app.exec_())
