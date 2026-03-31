from chemunited.shared.graph import GraphCore
from chemunited.shared.enums import SetupStepMode


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

