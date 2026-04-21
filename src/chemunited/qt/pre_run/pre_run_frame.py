from PyQt5.QtWidgets import QFrame, QHBoxLayout


class PreRunFrame(QFrame):

    def __init__(self, parent):
        super().__init__(parent)
        self.parent_ref = parent
        self.main_layout = QHBoxLayout(self)

        self.init_ui()

    def init_ui(self):
        ...
