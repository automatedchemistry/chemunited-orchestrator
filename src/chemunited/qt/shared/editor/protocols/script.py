from pathlib import Path

import black  # type: ignore[import-not-found]
from loguru import logger
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QDockWidget, QHBoxLayout, QMainWindow, QWidget
from qfluentwidgets import FluentIcon, NavigationInterface, NavigationItemPosition

from chemunited.qt.shared.editor.base import EditorBase
from chemunited.qt.shared.editor.protocols.command_list import CommandList
from chemunited.qt.shared.icon import OrchestratorIcon
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chemunited.qt.setup import SetupWindow


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

        self.editor = self._make_editor(path)

        self.navigationInterface = NavigationInterface(self, showMenuButton=True)

        self.parent_ref = parent

        # --- central widget ---
        self.initlayout()

        self.initNavigation()

        # --- command dock ---
        self.command_list = CommandList(parent=self)

        self.command_dock = QDockWidget("Commands", self)
        self.command_dock.setWidget(self.command_list)
        self.command_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)  # type: ignore[attr-defined]
        self.addDockWidget(Qt.RightDockWidgetArea, self.command_dock)  # type: ignore[attr-defined]
        self.command_dock.hide()

        self.command_list.command_activated.connect(self._insert_command)

    def _make_editor(self, path: Path) -> EditorBase:
        return ScriptEditor(path=path, parent=self)

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

    def _find_orchestrator(self):
        obj = self.parent()
        while obj is not None:
            orchestrator = getattr(obj, "orchestrator", None)
            if orchestrator is not None:
                return orchestrator
            obj = obj.parent()
        return None

    def add_command_window(self):
        if self.command_dock.isVisible():
            self.command_dock.hide()
        else:
            orchestrator = self._find_orchestrator()
            if orchestrator is not None:
                self.command_list.parent_ref = orchestrator.parent()
            self.command_list.sync_protocols()
            self.command_dock.show()

    def _insert_command(self, line_script: str):
        line, col = self.editor.getCursorPosition()
        self.editor.insertAt(line_script + "\n", line, col)

    def add_process_parameter(self):
        pass

    def add_main_parameter(self):
        pass

    def closeEvent(self, event):
        """Override close event to handle custom cleanup."""
        self.command_dock.close()
        super().closeEvent(event)


if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv)
    window = ScriptEditorWindow(Path(__file__).parent / "example.py")
    window.show()
    sys.exit(app.exec_())
