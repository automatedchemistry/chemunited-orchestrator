from chemunited_core.elements.metadata import ComponentData
from .graph import GraphComponent


class UtensilManager:
    def __init__(self):
        """Figure"""
        self.graph: GraphComponent = GraphComponent()

    @property
    def name(self) -> str:
        return self.graph.mdata.name

    @property
    def inf(self) -> ComponentData:
        """Metadata information"""
        return self.graph.mdata


class ElectronicManager(UtensilManager):
    def __init__(self):
        super().__init__()
