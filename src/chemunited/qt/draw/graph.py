from chemunited.qt.shared.enums import SetupStepMode
from chemunited.qt.shared.graph import GraphCore, SceneCore
from typing import TYPE_CHECKING, override
from .tree_add import TreeAddItem

if TYPE_CHECKING:
    from ..setup import SetupWindow


class DrawGraphicView(GraphCore):
    MODE = SetupStepMode.DESIGN

    def __init__(self, scene: SceneCore | None = None, parent=None):
        super().__init__(scene, parent)
        self.setObjectName("drawGraph")
        if parent is not None:
            self.parent_ref: SetupWindow = parent

    @override
    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(TreeAddItem.MIME):
            event.acceptProposedAction()
        else:
            event.ignore()

    @override
    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(TreeAddItem.MIME):
            event.acceptProposedAction()
        else:
            event.ignore()

    @override
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

        if self.parent_ref is not None:
            self.parent_ref.orchestrator.request_add_component(
                figure=component, position=(scene_pos.x(), scene_pos.y())
            )

        event.acceptProposedAction()
