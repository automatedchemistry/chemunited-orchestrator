from chemunited.shared.enums import SetupStepMode
from chemunited.shared.graph import GraphCore, SceneCore


class SimGraphicView(GraphCore):
    MODE = SetupStepMode.DESIGN

    def __init__(self, scene: SceneCore | None = None, parent=None):
        super().__init__(scene, parent)
        self.setObjectName("SimGraphicView")
