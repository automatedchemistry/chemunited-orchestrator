from .shared.widgets.main_window import MainWindowBase


class MainWindow(MainWindowBase):
    TITLE = "ChemUnited Orchestrator"
    WINDOW_TYPE = WindowCategory.SETUP

    def __init__(self):
        super().__init__()

        