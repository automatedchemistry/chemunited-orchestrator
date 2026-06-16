from typing import Union

import chemunited_core.protocols as protocol_module
from chemunited_core.components import ComponentData
from chemunited_core.figure_registry import COMPONENTS
from chemunited_core.protocols import ComponentProtocol
from loguru import logger
from pydantic import AnyHttpUrl

from chemunited.elements.component.connectivity import ComponentConnnectivity

from . import glossary
from .graph_item import GraphComponent
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


# Cache for dynamically-created classes so __init_subclass__ only runs once per figure.
_dynamic_class_cache: dict[str, type[GraphComponent]] = {}


def _build_explicit_map() -> dict[str, type[GraphComponent]]:
    """Return {figure_key: cls} for every explicit GraphComponent subclass in the glossary."""
    result: dict[str, type[GraphComponent]] = {}
    for name in getattr(glossary, "__all__", []):
        cls = getattr(glossary, name, None)
        if isinstance(cls, type) and issubclass(cls, GraphComponent) and cls.FIGURE:
            result[cls.FIGURE] = cls
    return result


def _get_base_for(figure: str) -> type[GraphComponent]:
    """Return the appropriate GraphComponent base for a given figure.

    Rotary-valve figures must extend RotaryValveGraph so they inherit its
    stator/rotor rendering logic. All other figures use GraphComponent directly.
    Rotary valves are identified by figure_base == "RotaryValve" in the registry.
    """
    from chemunited.elements.component.glossary.valve.rotary_valve_graph import (
        RotaryValveGraph,
    )

    defn = COMPONENTS[figure]
    if (defn.figure_base or figure) == "RotaryValve":
        return RotaryValveGraph  # type: ignore[return-value]
    return GraphComponent


def _get_component_class(
    figure: str, explicit: dict[str, type[GraphComponent]]
) -> type[GraphComponent]:
    if figure in explicit:
        return explicit[figure]
    if figure not in _dynamic_class_cache:
        base = _get_base_for(figure)
        _dynamic_class_cache[figure] = type(figure, (base,), {"FIGURE": figure})
    return _dynamic_class_cache[figure]


def list_components() -> tuple[dict[str, list[str]], dict[str, type[GraphComponent]]]:
    """
    Returns (categories, components) where:
      categories: dict[category_name, sorted list of figure names]
      components: dict[figure_name, GraphComponent subclass]

    The component list is driven by core's COMPONENTS registry. Explicit orchestrator
    subclasses (those in glossary/__all__ with a FIGURE declaration) are used when
    available; everything else gets a dynamically-created subclass wired via
    __init_subclass__.
    """
    explicit = _build_explicit_map()
    categories: dict[str, list[str]] = {}
    components: dict[str, type[GraphComponent]] = {}

    for figure_name, defn in COMPONENTS.items():
        cls = _get_component_class(figure_name, explicit)
        components[figure_name] = cls
        category = defn.category or "other"
        categories.setdefault(category, []).append(figure_name)

    return {k: sorted(v) for k, v in sorted(categories.items())}, components


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
