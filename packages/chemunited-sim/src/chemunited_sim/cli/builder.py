"""PlatformBuilder — constructs ComponentData and EdgeData from a draw/setup.py."""

from __future__ import annotations

from chemunited_core.common.enums import ConnectionType, PhaseKind
from chemunited_core.components import ComponentData, NeutralComponentData
from chemunited_core.components.internals import DEFAULT_INVENTORY_KEY
from chemunited_core.compounds import COMPOUNDS, ChemicalEntity
from chemunited_core.connections.edge import EdgeData, EdgeMode
from chemunited_core.figure_registry import COMPONENTS
from chemunited_core.figure_registry.vessels import FlowReactorData
from chemunited_quantities import ChemUnitQuantity
from loguru import logger

from ..reactions import FirstOrderDecay, ReactionsMap


def _quantity(value: float | str | ChemUnitQuantity, unit: str) -> ChemUnitQuantity:
    if isinstance(value, ChemUnitQuantity):
        return value
    return ChemUnitQuantity(value, unit)


class PlatformBuilder:
    """Accumulates components and edges produced by build_draw(platform).

    Mirrors the API expected by draw/setup.py scripts so they can be run
    in-process instead of through the GUI.
    """

    def __init__(self) -> None:
        self._components: dict[str, ComponentData] = {}
        self._edges: list[EdgeData] = []
        self._reactions_map: ReactionsMap = {}

    def add_component(
        self,
        name: str,
        figure: str,
        position: tuple[float, float] = (0.0, 0.0),
        angle: int = 0,
        **kwargs,
    ) -> ComponentData:
        if figure not in COMPONENTS:
            raise ValueError(
                f"Unknown figure '{figure}'. Available: {list(COMPONENTS)}"
            )
        if name in self._components:
            raise ValueError(f"Duplicate component name '{name}'")

        defn = COMPONENTS[figure]
        data_cls, mode_cls = defn.data_class, defn.mode_class
        mode = mode_cls(name=name, position=position, angle=angle, **kwargs)
        data = data_cls.from_mode(mode)
        self._components[name] = data
        logger.debug("Component added | name='{}' figure='{}'", name, figure)
        return data

    def add_connection(
        self,
        origin: str,
        destiny: str,
        origin_port: int,
        destiny_port: int,
        **kwargs,
    ) -> EdgeData:
        length = kwargs.pop("length", "100 mm")
        diameter = kwargs.pop("diameter", "1 mm")
        classification = kwargs.pop("classification", ConnectionType.HYDRAULIC)
        kwargs.pop("name", None)

        mode = EdgeMode(
            origin=origin,
            destination=destiny,
            origin_port=origin_port,
            destination_port=destiny_port,
            length=length,
            diameter=diameter,
            classification=classification,
            **kwargs,
        )
        edge = EdgeData.from_mode(mode)
        self._edges.append(edge)
        logger.debug(
            "Edge added | {}.{} -> {}.{}", origin, origin_port, destiny, destiny_port
        )
        return edge

    def add_compound(
        self,
        name: str = "reagent_a",
        molecular_weight: float | str | ChemUnitQuantity = 120.0,
        cp_liquid: float | str | ChemUnitQuantity = 150.0,
        density_liquid: float | str | ChemUnitQuantity = 1050.0,
        cp_gas: float | str | ChemUnitQuantity = 29.0,
        **kwargs,
    ) -> None:
        if name in COMPOUNDS:
            raise ValueError(f"Compound '{name}' already exists")
        COMPOUNDS.register(
            ChemicalEntity(
                name=name,
                molecular_weight=_quantity(molecular_weight, "g/mol"),
                cp_liquid=_quantity(cp_liquid, "J/(mol*K)"),
                cp_gas=_quantity(cp_gas, "J/(mol*K)"),
                density_liquid=_quantity(density_liquid, "kg/m^3"),
                **kwargs,
            )
        )
        logger.debug("Compound registered | name='{}' MW={}", name, molecular_weight)

    def add_reaction(
        self,
        target: str,
        reaction_type: str,
        reactant: str,
        product: str,
        rate_constant: float,
        phase: str | PhaseKind = "LIQUID",
        delta_temperature_per_mol_converted: float = 0.0,
    ) -> None:
        if reaction_type != "FirstOrderDecay":
            raise ValueError(
                f"Unknown reaction_type '{reaction_type}'. "
                "Only 'FirstOrderDecay' is supported."
            )
        component = self._components.get(target)
        if component is None:
            raise ValueError(f"Unknown reaction target '{target}'")
        if isinstance(component, FlowReactorData):
            target_id = f"{target}.1.2"
        elif DEFAULT_INVENTORY_KEY in component.internal_inventories:
            target_id = f"{target}.{DEFAULT_INVENTORY_KEY}"
        else:
            raise ValueError(
                f"Component '{target}' does not support reactions. "
                "Expected a vessel inventory or FlowReactor."
            )
        phase_kind = PhaseKind(phase.lower()) if isinstance(phase, str) else phase
        reaction = FirstOrderDecay(
            reactant=reactant,
            product=product,
            rate_constant=rate_constant,
            phase=phase_kind,
            delta_temperature_per_mol_converted=delta_temperature_per_mol_converted,
        )
        self._reactions_map.setdefault(target_id, []).append(reaction)
        logger.debug(
            "Reaction added | target='{}' type='{}' reactant='{}' -> product='{}'",
            target,
            reaction_type,
            reactant,
            product,
        )

    def fill_iventory(self, component: str, iventory: str, phase: str, content: dict):
        if component not in self._components:
            return
        node = self._components[component].internal_inventories.get(iventory)
        if node is None:
            return
        phase_content = node.liq_content if phase == "liq" else node.gas_content
        if "volume" in content:
            phase_content.volume = float(content["volume"])
        if "initial_species" in content:
            phase_content.initial_species = {
                str(k): float(v)
                for k, v in content["initial_species"].items()
                if float(v) > 0.0
            }
        if "initial_pressure" in content:
            phase_content.initial_pressure = float(content["initial_pressure"])
        if "initial_temperature" in content:
            phase_content.initial_temperature = float(content["initial_temperature"])

    @property
    def reactions_map(self) -> ReactionsMap:
        return dict(self._reactions_map)

    def add_component_data(self, data: ComponentData) -> ComponentData:
        """Add a pre-created ComponentData directly, bypassing the figure registry."""
        if data.name in self._components:
            raise ValueError(f"Duplicate component name '{data.name}'")
        self._components[data.name] = data
        return data

    def __getitem__(self, name: str) -> ComponentData:
        return self._components[name]

    @property
    def hydraulic_components(self) -> list[ComponentData]:
        return [
            c
            for c in self._components.values()
            if not isinstance(c, NeutralComponentData)
        ]

    @property
    def components(self) -> list[ComponentData]:
        return list(self._components.values())

    @property
    def edges(self) -> list[EdgeData]:
        return list(self._edges)
