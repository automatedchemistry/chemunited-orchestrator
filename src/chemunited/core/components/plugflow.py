"""Plug-flow transport component — tube, capillary, or flow reactor channel.

Represents any tubular element where material travels as an ordered plug
without mixing. Compiles into a single TRANSPORT edge between two ports.
Hydraulic resistance is computed by the sim solver from length and diameter
using the Hagen-Poiseuille equation.

GUI: exposes length and diameter in the properties widget.
Sim: InternalEdge.length and diameter are the primary inputs to the
     resistance calculation and the parcel travel-time estimate.
"""
from dataclasses import dataclass
from typing import Annotated

import numpy as np
from pydantic import Field

from chemunited_core.common.enums import GroupParameterCategory
from chemunited_core.utils.internal_quantity import ChemQuantityValidator, ChemUnitQuantity
from .component import ComponentData, ComponentMode
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
    length: ChemUnitQuantity = ChemUnitQuantity("100 mm")
    diameter: ChemUnitQuantity = ChemUnitQuantity("1 mm")

    @property
    def capacity(self) -> float:
        return self.length_value * np.pi * self.diameter**2 / 4  # m**3

    @property
    def length_value(self) -> float:
        return self.length.to_base_units().magnitude

    @property
    def diameter_value(self) -> float:
        return self.diameter.to_base_units().magnitude

    def internal_structure(self):
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

    def sync_internal_state(self):
        edge = self.internal_edges.get((1, 2))
        edge.length = self.length_value
        edge.diameter = self.diameter_value
