from chemunited.qt.shared.widgets.base_mode_editor import BaseModeDialog


class NewVariableDialog(BaseModeDialog):
    def __init__(self, parent=None, title: str = "", baseConfig=None):
        super().__init__(parent=parent, title=title, baseConfig=baseConfig)