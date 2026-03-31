from PyQt5.QtCore import QMimeData, QObject

from chemunited.qt.shared.enums import SetupStepMode
from chemunited.qt.shared.graph import GraphCore


class TreeAddItem(QObject):
    MIME = "application/x-tree-add-item"

    def __init__(self, group: str, component: str, parent: QObject | None = None):
        super().__init__(parent)
        self.group = group
        self.component = component

    def mimeData(self) -> QMimeData:
        data = QMimeData()
        data.setData(self.MIME, f"{self.group}|{self.component}".encode("utf-8"))
        return data

    def mimeType(self) -> str:
        return self.MIME


class DrawGraphicView(GraphCore):
    MODE = SetupStepMode.DESIGN

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(TreeAddItem.MIME):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(TreeAddItem.MIME):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if not event.mimeData().hasFormat(TreeAddItem.MIME):
            event.ignore()
            return

        data = bytes(event.mimeData().data(TreeAddItem.MIME)).decode(
            "utf-8"
        )  # "group|component"
        if "|" not in data:
            event.ignore()
            return

        group, component = data.split("|", 1)

        scene_pos = self.mapToScene(event.pos())

        print(f"Component: {component}, Group: {group}, Position: {scene_pos}")

        event.acceptProposedAction()
