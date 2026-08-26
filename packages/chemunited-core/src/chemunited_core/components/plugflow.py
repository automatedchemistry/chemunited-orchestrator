"""Plug-flow transport component — tube, capillary, or flow reactor channel.

Represents any tubular element where material travels as an ordered plug
without mixing. Compiles into a single TRANSPORT edge between two ports.
Hydraulic resistance is computed by the sim solver from length and diameter
using the Hagen-Poiseuille equation.

GUI: exposes length and diameter in the properties widget.
Sim: InternalEdge.length and diameter are the primary inputs to the
     resistance calculation and the parcel travel-time estimate.
"""

import math
from dataclasses import dataclass, field
from typing import Annotated, ClassVar

import numpy as np
from chemunited_quantities import (
    ChemQuantityValidator,
    ChemUnitQuantity,
)
from pydantic import Field
from typing_extensions import override

from chemunited_core.common.constant import (
    AMBIENT_TEMPERATURE_K,
    ATMOSPHERE_PRESSURE_PA,
)
from chemunited_core.common.enums import GroupParameterCategory, PhaseKind
from chemunited_core.compounds.entity import IDEAL_GAS_CONSTANT
from chemunited_core.compounds.pockets import VolumeContentBase

from .component import ComponentData, ComponentMode
from .enums import ComponentType
from .internals import InternalEdge, Port


class PlugFlowMode(ComponentMode):
    """User-configurable geometry for a plug-flow component.
    length   — channel length (default 100 mm).
    diameter — channel inner diameter (default 1 mm).
    """

    length: Annotated[ChemUnitQuantity, ChemQuantityValidator("mm")] = Field(
        default=ChemUnitQuantity("100 mm"),
        title="Length",
        description="Length of the connection",
        json_schema_extra={
            "group": GroupParameterCategory.PROPERTY.value,
        },
    )
    diameter: Annotated[ChemUnitQuantity, ChemQuantityValidator("mm")] = Field(
        default=ChemUnitQuantity("1 mm"),
        title="Diameter",
        description="Diameter of the connection",
        json_schema_extra={
            "group": GroupParameterCategory.PROPERTY.value,
        },
    )


@dataclass
class PlugFlowComponentData(ComponentData):
    """Structural definition of a tubular plug-flow element.

    Internal subgraph: one TRANSPORT edge between port 1 (inlet) and
    port 2 (outlet). Edge length and diameter are updated by
    sync_internal_state() when the user changes geometry in the GUI.
    """

    COMPONENT_TYPE: ClassVar[ComponentType] = ComponentType.UTENSIL
    length: ChemUnitQuantity = ChemUnitQuantity("100 mm")
    diameter: ChemUnitQuantity = ChemUnitQuantity("1 mm")
    content: list[VolumeContentBase] = field(default_factory=list, init=False)

    def apply_air_defaults(self) -> None:
        """Fill content with one air segment if the user declared nothing."""
        if self.content:
            return
        volume = math.pi * (self.diameter_value / 2.0) ** 2 * self.length_value
        if volume <= 0.0:
            return
        n_air = (
            ATMOSPHERE_PRESSURE_PA
            * volume
            / (IDEAL_GAS_CONSTANT * AMBIENT_TEMPERATURE_K)
        )
        self.content = [
            VolumeContentBase(
                phase_kind=PhaseKind.GAS,
                volume=volume,
                initial_species={"air": n_air},
                initial_pressure=ATMOSPHERE_PRESSURE_PA,
                initial_temperature=AMBIENT_TEMPERATURE_K,
            )
        ]

    @property
    def capacity(self) -> float:
        return float(self.length_value * np.pi * self.diameter**2 / 4)  # m**3

    @property
    def length_value(self) -> float:
        return float(self.length.to_base_units().magnitude)

    @property
    def diameter_value(self) -> float:
        return float(self.diameter.to_base_units().magnitude)

    @override
    def internal_structure(self) -> None:
        self.port_pairs = [(1, 2)]
        self.ports_by_number = {
            1: Port(number=1, component=self.name, relative_position=(-1, 0)),
            2: Port(number=2, component=self.name, relative_position=(1, 0)),
        }
        self.internal_edges = {
            (1, 2): InternalEdge(
                origin_port=1,
                destination_port=2,
                length=self.length_value,
                diameter=self.diameter_value,
            )
        }

    @override
    def sync_internal_state(self) -> None:
        edge = self.internal_edges[(1, 2)]
        edge.length = self.length_value
        edge.diameter = self.diameter_value
