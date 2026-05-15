from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QFrame, QSizePolicy, QSpacerItem, QVBoxLayout
from qfluentwidgets import PushButton

from .list import ProcessList


class ProcessWidget(QFrame):
    """Concrete visual shell: wraps any ProcessList with a separator and button bar."""

    selection_changed = pyqtSignal(str)
    process_renamed = pyqtSignal(str, str)

    def __init__(self, process_list: ProcessList, parent=None) -> None:
        super().__init__(parent)
        self._list = process_list
        self._list.selection_changed.connect(self.selection_changed)  # type: ignore[attr-defined]
        self._list.process_renamed.connect(self.process_renamed)  # type: ignore[attr-defined]

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._list, stretch=1)

        separator = QFrame(self)
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setFixedHeight(1)
        outer.addWidget(separator)

        self._btn_layout = QVBoxLayout()
        self._btn_layout.setContentsMargins(8, 6, 8, 6)
        self._btn_layout.setSpacing(4)
        self._btn_layout.addItem(
            QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Minimum)
        )
        outer.addLayout(self._btn_layout)

    def add_bottom_button(self, name: str, icon, tip: str, callable) -> PushButton:
        btn = PushButton(icon, name, self)
        btn.setToolTip(tip)
        btn.clicked.connect(callable) # type: ignore[attr-defined]
        count = self._btn_layout.count()
        self._btn_layout.insertWidget(count - 1, btn, alignment=Qt.AlignCenter)  # type: ignore[attr-defined]
        return btn

    def add_separator(self) -> None:
        sep = QFrame(self)
        sep.setFrameShape(QFrame.VLine)
        sep.setFrameShadow(QFrame.Sunken)
        sep.setFixedWidth(1)
        count = self._btn_layout.count()
        self._btn_layout.insertWidget(count - 1, sep, alignment=Qt.AlignCenter)  # type: ignore[attr-defined]

    def sync_list(self):
        self._list.sync()


if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication
    from qfluentwidgets import FluentIcon

    class DemoList(ProcessList):
        def __init__(self, data, parent=None):
            super().__init__(data, parent)
            self.set_items_renameable(True)
            self.add_items_option("Remove", FluentIcon.DELETE, "Remove this process")
            self._dispatch["Remove"] = self._on_remove

        def _on_remove(self, name: str):
            self.remove_process(name)

    app = QApplication(sys.argv)

    data = {"Calibration": None, "Clean": None, "React": None}
    lst = DemoList(data)
    widget = ProcessWidget(lst)

    widget.add_bottom_button(
        "Add",
        FluentIcon.ADD,
        "Add a new process",
        lambda: lst.add_process(f"process_{len(data)}"),
    )
    widget.add_separator()
    widget.add_bottom_button(
        "Remove",
        FluentIcon.DELETE,
        "Remove selected process",
        lambda: (
            lst.remove_process(lst.selected_name()) if lst.selected_name() else None
        ),
    )

    widget.selection_changed.connect(lambda name: print(f"Selected: {name!r}")) # type: ignore[attr-defined]
    widget.process_renamed.connect(  # type: ignore[attr-defined]
        lambda old, new: print(f"Renamed: {old!r} -> {new!r}")
    )

    widget.resize(320, 480)
    widget.show()
    sys.exit(app.exec_())
