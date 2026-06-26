from chemunited.shared.graph import GraphCore, SceneCore
from chemunited.shared.enums import SetupStepMode


class SimGraphicView(GraphCore):
    MODE = SetupStepMode.DESIGN

    def __init__(self, scene: SceneCore | None = None, parent=None):
        super().__init__(scene, parent)
        self.setObjectName("SimGraphicView")