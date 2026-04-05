from chemunited.qt.shared.widgets.base_mode_editor.cards.builder_models import (
    StringVariableBuildMode,
    IntVariableBuildMode,
    FloatVariableBuildMode,
    ListVariableBuildMode,
    ChoiceVariableBuildMode,
    PhysicalQuantitiesMode,
)
from chemunited.qt.shared.editor.parameters.dialog import NewVariableDialog
from chemunited.qt.shared.icon import OrchestratorIcon
from chemunited.qt.shared.editor.base import EditorBase
from qfluentwidgets import NavigationInterface, NavigationItemPosition, FluentIcon
from PyQt5.QtWidgets import QMainWindow, QWidget, QHBoxLayout
from functools import partial
from loguru import logger
from PyQt5.QtGui import QIcon
from pathlib import Path
import black


class Editor(EditorBase):
    def __init__(self, path: Path, parent=None):
        super().__init__(parent=parent, path=path)
        self._load_content()


class MainParametersEditor(QMainWindow):
    def __init__(self, path: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Parameters Editor")
        self.setWindowIcon(QIcon(OrchestratorIcon.CHEMUNITED.path()))
        self.resize(800, 600)  # optional default size
        self.setMinimumSize(600, 600)

        self.editor = Editor(parent=self, path=path)

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
            routeKey="New integer variable",
            icon=OrchestratorIcon.INTEGER,
            text="New integer variable",
            onClick=partial(self.__new_variable, IntVariableBuildMode()),
            selectable=False,
            tooltip="New integer variable",
        )

        self.navigationInterface.addItem(
            routeKey="New float variable",
            icon=FluentIcon.SKIP_BACK,
            text="New float variable",
            onClick=partial(self.__new_variable, FloatVariableBuildMode()),
            selectable=False,
            tooltip="New float variable",
        )

        self.navigationInterface.addItem(
            routeKey="New string variable",
            icon=OrchestratorIcon.STRING,
            text="New string variable",
            onClick=partial(self.__new_variable, StringVariableBuildMode()),
            selectable=False,
            tooltip="New string variable",
        )

        self.navigationInterface.addItem(
            routeKey="New array variable",
            icon=OrchestratorIcon.LIST,
            text="New array variable",
            onClick=partial(self.__new_variable, ListVariableBuildMode()),
            selectable=False,
            tooltip="New array variable",
        )

        self.navigationInterface.addItem(
            routeKey="New choice variable",
            icon=OrchestratorIcon.CHOICES,
            text="New choice variable",
            onClick=partial(self.__new_variable, ChoiceVariableBuildMode()),
            selectable=False,
            tooltip="New choice variable",
        )

        self.navigationInterface.addItem(
            routeKey="New physical quantity",
            icon=OrchestratorIcon.MEASURE,
            text="New physical quantity",
            onClick=partial(self.__new_variable, PhysicalQuantitiesMode()),
            selectable=False,
            tooltip="New physical quantity variable",
        )
    
    def __new_variable(self, mode):
        if self.parent_ref:
            win = NewVariableDialog(
                parent=self,
                title=f"Build a new variable - {mode.__class__.__name__}",
                baseConfig=mode,
            )
            if win.exec():
                ...
    
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

if __name__ == "__main__":
    from PyQt5.QtWidgets import QApplication
    import sys
    app = QApplication(sys.argv)
    editor = MainParametersEditor(path=Path(__file__))
    editor.show()
    sys.exit(app.exec_())