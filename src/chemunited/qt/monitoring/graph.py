from typing import TYPE_CHECKING

from chemunited.qt.shared.graph import GraphCore, SceneCore

if TYPE_CHECKING:
    from ..monitor import MonitorWindow


class ExecutionGraph(GraphCore):
    def __init__(self, scene: SceneCore, parent=None):
        super().__init__(scene, parent)
        self.setObjectName("ExecutionGraph")
        if parent is not None:
            self.parent_ref: MonitorWindow = parent
