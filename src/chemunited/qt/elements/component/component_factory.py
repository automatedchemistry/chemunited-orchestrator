from typing import Union

from loguru import logger
from pydantic import AnyHttpUrl

import chemunited.qt.elements.component.protocols as protocol_module
from chemunited.core.components import ComponentData
from chemunited.qt.elements.component.connectivity import ComponentConnnectivity

from . import glossary
from .graph_item import GraphComponent
from .protocols import ComponentProtocol
from .widgets import ComponentWidget


class UtensilManager:
    def __init__(self):
        self.graph: GraphComponent
        self._widget: ComponentWidget | None = None  # lazy — created on first access

    @property
    def widget(self) -> ComponentWidget:
        if self._widget is None:
            self._widget = ComponentWidget(self)
        return self._widget

    @property
    def name(self) -> str:
        return self.graph._data.name

    @property
    def inf(self) -> ComponentData:
        return self.graph._data


class ElectronicManager(UtensilManager):
    def __init__(self):
        super().__init__()
        self.protocols: ComponentProtocol = ComponentProtocol("generic")
        self.connectivity: ComponentConnnectivity = ComponentConnnectivity()

    @property
    def url(self) -> AnyHttpUrl:
        """Get the url of the component."""
        return self.connectivity.url

    @url.setter
    def url(self, url: AnyHttpUrl):
        """Set the url of the component."""
        self.connectivity.url = url

    @property
    def is_online(self) -> bool:
        """Check if the component is online."""
        return self.connectivity.is_online

    @property
    def url_component(self) -> str:
        """Get the url of the component."""
        return self.connectivity.url_component


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


def create_component(figure: str, **kwargs) -> Union[UtensilManager, ElectronicManager]:
    _, components = list_components()
    if figure not in components:
        logger.error(f"Component {figure} not found, assuming generic component")
        fallback_component = ElectronicManager()
        fallback_component.graph = GraphComponent(
            ComponentData(
                name=kwargs.get("name", figure),
                figure=figure,
                position=kwargs.get("position", (0, 0)),
                angle=kwargs.get("angle", 0),
            )
        )
        return fallback_component
    mode = components[figure].BASEMODE.model_validate({"figure": figure, **kwargs})
    mdata = components[figure].METADATA.from_mode(mode)
    if mdata.is_electronic:
        electronic_component = ElectronicManager()
        electronic_component.graph = components[figure](mdata)
        protocol_cls = getattr(
            protocol_module,
            f"{mdata.figure}Protocols",
            ComponentProtocol,
        )
        electronic_component.protocols = protocol_cls(electronic_component.name)
        return electronic_component

    component = UtensilManager()
    component.graph = components[figure](mdata)
    return component
