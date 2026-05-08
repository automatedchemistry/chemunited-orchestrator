from typing import TYPE_CHECKING, override

from loguru import logger

from chemunited.qt.elements.component.graph_item import GraphComponent
from chemunited.qt.shared.enums import SetupStepMode
from chemunited.qt.shared.graph import GraphCore, SceneCore

from .online_list import OnlineList

if TYPE_CHECKING:
    from ..setup import SetupWindow


class ConnectivityGraphicView(GraphCore):
    MODE = SetupStepMode.CONNECTIVITY

    def __init__(self, scene: SceneCore | None = None, parent=None):
        super().__init__(scene, parent)
        self.setObjectName("ConnectivityGraphicView")
        if parent is not None:
            self.parent_ref: SetupWindow = parent

    @override
    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(OnlineList.MIME):
            event.acceptProposedAction()
        else:
            event.ignore()

    @override
    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(OnlineList.MIME):
            event.acceptProposedAction()
        else:
            event.ignore()

    def _component_at_drop_position(self, event) -> GraphComponent | None:
        scene_pos = self.mapToScene(event.pos())
        scene = self.scene()
        if scene is None:
            return None

        for item in scene.items(scene_pos):
            current = item
            while current is not None:
                if isinstance(current, GraphComponent):
                    return current
                current = current.parentItem()
        return None

    @override
    def dropEvent(self, event):
        if not event.mimeData().hasFormat(OnlineList.MIME):
            event.ignore()
            return

        url_component = event.mimeData().data(OnlineList.MIME).data().decode("utf-8")
        event.acceptProposedAction()

        component = self._component_at_drop_position(event)
        if component is None:
            logger.warning(
                f"No component found at position {self.mapToScene(event.pos())}"
            )
            return
        if not component.inf.is_electronic:
            logger.warning(f"Component {component.inf.name} is not electronic.")
            return

        if hasattr(self, "parent_ref"):
            self.parent_ref.orchestrator.associate_component(
                name=component.inf.name,
                urlc=url_component,
            )
        else:
            print(url_component, component.inf.name)
