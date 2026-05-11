from pathlib import Path
from typing import TYPE_CHECKING

import black  # type: ignore[import-not-found]
from loguru import logger
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QDropEvent, QIcon
from PyQt5.QtWidgets import QDockWidget, QHBoxLayout, QMainWindow, QWidget
from qfluentwidgets import FluentIcon, NavigationInterface, NavigationItemPosition

from chemunited.qt.shared.editor.base import EditorBase
from chemunited.qt.shared.editor.parameters.drag_list import ParameterDragableList
from chemunited.qt.shared.editor.protocols.command_list import CommandList
from chemunited.qt.shared.icon import OrchestratorIcon

if TYPE_CHECKING:
    pass


class ScriptEditor(EditorBase):
    def __init__(self, path: Path, parent=None):
        super().__init__(parent, path=path)

    def dropEvent(self, event: QDropEvent) -> None:
        mime_data = event.mimeData()
        if mime_data.hasFormat(ParameterDragableList.MIME) and mime_data.hasFormat(
            ParameterDragableList.PATH_MIME
        ):
            source_path = Path(
                bytes(mime_data.data(ParameterDragableList.PATH_MIME)).decode("utf-8")
            ).resolve()
            current_path = self.path.resolve()
            if source_path != current_path and source_path.name != "main_parameters.py":
                event.ignore()
                return

        super().dropEvent(event)


class ScriptEditorWindow(QMainWindow):
    def __init__(
        self,
        path: Path,
        class_name: str | None = None,
        main_parameters_path: Path | None = None,
        parent=None,
    ):
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

        # --- process parameter dock ---
        self.process_parameter_editor = ParameterDragableList(
            path=path,
            class_name=f"{class_name}Config" if class_name else "MainParameter",
            parent=self,
        )
        self.process_parameter_dock = QDockWidget("Process Parameters", self)
        self.process_parameter_dock.setWidget(self.process_parameter_editor)
        self.process_parameter_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)  # type: ignore[attr-defined]
        self.addDockWidget(Qt.RightDockWidgetArea, self.process_parameter_dock)  # type: ignore[attr-defined]
        self.process_parameter_dock.hide()

        # --- main parameter dock ---
        self.main_parameter_editor: ParameterDragableList | None
        self.main_parameter_dock: QDockWidget | None
        if main_parameters_path is not None:
            self.main_parameter_editor = ParameterDragableList(
                path=main_parameters_path,
                class_name="MainParameter",
                parent=self,
            )
            self.main_parameter_dock = QDockWidget("Main Parameters", self)
            self.main_parameter_dock.setWidget(self.main_parameter_editor)
            self.main_parameter_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)  # type: ignore[attr-defined]
            self.addDockWidget(Qt.RightDockWidgetArea, self.main_parameter_dock)  # type: ignore[attr-defined]
            self.main_parameter_dock.hide()
        else:
            self.main_parameter_editor = None
            self.main_parameter_dock = None

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
        if self.process_parameter_dock.isVisible():
            self.process_parameter_dock.hide()
        else:
            self.process_parameter_editor.reload()
            self.process_parameter_dock.show()

    def add_main_parameter(self):
        if self.main_parameter_dock is None or self.main_parameter_editor is None:
            return
        if self.main_parameter_dock.isVisible():
            self.main_parameter_dock.hide()
        else:
            self.main_parameter_editor.reload()
            self.main_parameter_dock.show()

    def closeEvent(self, event):
        """Override close event to handle custom cleanup."""
        self.command_dock.close()
        self.process_parameter_dock.close()
        if self.main_parameter_dock is not None:
            self.main_parameter_dock.close()
        super().closeEvent(event)


if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv)
    window = ScriptEditorWindow(
        path=Path(__file__).parent / "example.py",
        class_name="CustomProcess",
        main_parameters_path=Path(__file__).parent.parent / "parameters" / "example.py",
    )
    window.show()
    sys.exit(app.exec_())
