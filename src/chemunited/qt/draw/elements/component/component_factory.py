from chemunited.core.components import ComponentData, NeutralComponentData

from . import glossary
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


def list_components() -> tuple[dict[str, list[str]], dict[str, type[GraphComponent]]]:
    """
    the category is the name of the folder in the glossary
    the component name is the name of object in __all__ of the glossary module
    dict[category, [ComponentName, ComponentName2, ...]], dict[ComponentName, ComponentObject]
    """
    categories: dict[str, list[str]] = {}
    components: dict[str, type[GraphComponent]] = {}

    glossary_prefix = f"{glossary.__name__}."

    for component_name in getattr(glossary, "__all__", []):
        component = getattr(glossary, component_name, None)
        if not isinstance(component, type) or not issubclass(component, GraphComponent):
            continue

        module_name = component.__module__
        if module_name.startswith(glossary_prefix):
            category = module_name.removeprefix(glossary_prefix).split(".", 1)[0]
        else:
            category = "uncategorized"

        categories.setdefault(category, []).append(component_name)
        components[component_name] = component

    ordered_categories = {
        category: sorted(component_names)
        for category, component_names in sorted(categories.items())
    }

    return ordered_categories, components
