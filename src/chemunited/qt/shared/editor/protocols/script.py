from pathlib import Path

import black  # type: ignore[import-not-found]
from loguru import logger
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QHBoxLayout, QMainWindow, QWidget
from qfluentwidgets import FluentIcon, NavigationInterface, NavigationItemPosition

from chemunited.qt.shared.editor.base import EditorBase
from chemunited.qt.shared.icon import OrchestratorIcon


class ScriptEditor(EditorBase):
    def __init__(self, path: Path, parent=None):
        super().__init__(parent, path=path)


class ScriptEditorWindow(QMainWindow):
    def __init__(self, path: Path, parent=None):
        super().__init__(parent)

        # --- window setup ---
        self.setWindowTitle(f"Script Editor: {path}")
        self.setWindowIcon(QIcon(OrchestratorIcon.CHEMUNITED.path()))
        self.resize(800, 600)  # optional default size
        self.setMinimumSize(600, 600)

        self.editor = ScriptEditor(path=path, parent=self)

        self.navigationInterface = NavigationInterface(self, showMenuButton=True)

        # --- central widget ---
        self.initlayout()

        self.initNavigation()

    def initlayout(self):

        # --- central widget ---
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        self.hBoxLayout = QHBoxLayout(central_widget)

        self.hBoxLayout.addWidget(self.editor)
        self.hBoxLayout.addWidget(self.navigationInterface)
        self.hBoxLayout.setContentsMargins(0, 0, 0, 0)
        self.hBoxLayout.setSpacing(0)

    def initNavigation(self):
        """Initializes the navigation interface by adding home and custom buttons."""
        self.navigationInterface.addItem(
            routeKey="Save",
            icon=FluentIcon.SAVE,
            text="Save",
            onClick=self.save,
            selectable=False,
            position=NavigationItemPosition.BOTTOM,
            tooltip="Save",
        )

        self.navigationInterface.addItem(
            routeKey="Set Black Format",
            icon=FluentIcon.BROOM,
            text="Set Black Format",
            onClick=self.format_with_black,
            selectable=False,
            position=NavigationItemPosition.BOTTOM,
            tooltip="Set Black Format",
        )

        self.navigationInterface.addItem(
            routeKey="Add Command",
            icon=OrchestratorIcon.PLAY,
            text="Add Command",
            onClick=self.add_command_window,
            selectable=False,
            tooltip="Add new command",
        )

        self.navigationInterface.addItem(
            routeKey="Add Process Parameter",
            icon=OrchestratorIcon.PROCESS,
            text="Add Process Parameter",
            onClick=self.add_process_parameter,
            selectable=False,
            tooltip="Add Process Parameter",
        )

        self.navigationInterface.addItem(
            routeKey="Add Main Parameter",
            icon=OrchestratorIcon.VARIABLE,
            text="Add Main Parameter",
            onClick=self.add_main_parameter,
            selectable=False,
            tooltip="Add Main Parameter",
        )

    def save(self):
        self.editor.autosave()

    def format_with_black(self):
        """Apply Black formatting to the code in a QsciScintilla editor."""
        try:
            code = self.editor.text()
            # Apply Black formatting
            formatted = black.format_str(code, mode=black.Mode())
            # Update editor only if changed
            if formatted != code:
                cursor_pos = self.editor.getCursorPosition()
                self.editor.setText(formatted)
                self.editor.setCursorPosition(*cursor_pos)
        except black.NothingChanged:
            pass  # code is already formatted
        except Exception as e:
            logger.opt(exception=e).error(
                "Black formatting failed, more detail go to loggings window"
            )

    def add_command_window(self):
        pass

    def add_process_parameter(self):
        pass

    def add_main_parameter(self):
        pass


if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv)
    window = ScriptEditorWindow(Path(__file__).parent / "example.py")
    window.show()
    sys.exit(app.exec_())
