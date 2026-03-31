from chemunited.core.components import ComponentData, NeutralComponentData

from .graph_item import GraphComponent


class UtensilManager:
    def __init__(self, data: ComponentData | None = None):
        """Figure"""
        self.graph = GraphComponent(data or NeutralComponentData())

    @property
    def name(self) -> str:
        return self.graph._data.name

    @property
    def inf(self) -> ComponentData:
        """Metadata information"""
        return self.graph._data


class ElectronicManager(UtensilManager):
    def __init__(self, data: ComponentData | None = None):
        super().__init__(data)
