from dataclasses import dataclass
from typing import Annotated, ClassVar

from chemunited_quantities import ChemQuantityValidator, ChemUnitQuantity
from pydantic import Field
from typing_extensions import override

from chemunited_core.common.constant import ATMOSPHERE_PRESSURE_PA, PATTERN_DIMENSION
from chemunited_core.common.enums import (
    ConnectionType,
    GroupParameterCategory,
    PhaseKind,
)
from chemunited_core.components import (
    PlugFlowComponentData,
    PlugFlowMode,
    VesselComponentData,
    VesselMode,
)
from chemunited_core.components.enums import (
    BoundaryConditionKind,
    ComponentType,
    InternalEdgeRole,
    PortAccess,
)
from chemunited_core.components.internals import (
    InternalEdge,
    InventoryNode,
    Port,
    PortBoundaryCondition,
)
from chemunited_core.compounds import VolumeContentBase

CELL_SIZE = 40
ROW_HEADER_WIDTH = 12
COLUMN_HEADER_HEIGHT = 12
HEAT_PORT_OFFSET = 14


class FlowReactorMode(PlugFlowMode):
    heat_exchange: bool = Field(
        default=False,
        title="Heat Exchange",
        description="Whether the component allows heat exchange.",
        json_schema_extra={
            "group": GroupParameterCategory.PROPERTY.value,
            "editable": False,
            "creation_editable": True,
            "lock_reason": "Internal Chosen",
        },
    )
    temperature: Annotated[ChemUnitQuantity, ChemQuantityValidator("K")] = Field(
        default=ChemUnitQuantity("298 K"),
        title="Temperature",
        description="Operating temperature of the component.",
        json_schema_extra={
            "group": GroupParameterCategory.STATUS.value,
        },
    )
    heat_transfer_coefficient: Annotated[
        ChemUnitQuantity, ChemQuantityValidator("W/(m^2*K)")
    ] = Field(
        default=ChemUnitQuantity("1000 W/(m^2*K)"),
        title="Heat Transfer Coefficient",
        description="Heat transfer coefficient for the component surface.",
        json_schema_extra={
            "group": GroupParameterCategory.PROPERTY.value,
        },
    )
    diameter: Annotated[ChemUnitQuantity, ChemQuantityValidator("m")] = Field(
        default=ChemUnitQuantity("0.05 m"),
        title="Diameter",
        description="Diameter of the component.",
        json_schema_extra={
            "group": GroupParameterCategory.PROPERTY.value,
        },
    )


@dataclass
class FlowReactorData(PlugFlowComponentData):
    heat_exchange: bool = True
    temperature: ChemUnitQuantity = ChemUnitQuantity("298 K")
    heat_transfer_coefficient: ChemUnitQuantity = ChemUnitQuantity("1000 W/(m^2*K)")
    diameter: ChemUnitQuantity = ChemUnitQuantity("0.05 m")

    @property
    def heat_transfer_coefficient_value(self) -> float:
        return float(self.heat_transfer_coefficient.to_base_units().magnitude)

    @property
    def temperature_value(self) -> float:
        return float(self.temperature.to_base_units().magnitude)

    def internal_structure(self) -> None:
        super().internal_structure()
        if self.heat_exchange:
            heat_port_number = max(self.ports_by_number.keys()) + 1
            self.ports_by_number[heat_port_number] = Port(
                number=heat_port_number,
                component=self.name,
                category=ConnectionType.HEAT,
                relative_position=(0, PATTERN_DIMENSION / 1.5),
            )
            self.port_pairs.append((heat_port_number,))


class PhotoReactorMode(FlowReactorMode): ...


@dataclass
class PhotoReactorData(FlowReactorData):
    COMPONENT_TYPE: ClassVar[ComponentType] = ComponentType.ELECTRONIC


class GlassBottleMode(VesselMode):
    top_access: int = Field(
        default=0,
        json_schema_extra={
            "visible": False,
        },
    )


@dataclass
class GlassBottleData(VesselComponentData):
    top_access: int = 0


def _position_to_letter(position: int) -> str:
    if position < 1:
        raise ValueError("Position must be >= 1")

    result = ""
    while position > 0:
        position -= 1
        result = chr(ord("A") + (position % 26)) + result
        position //= 26
    return result


def _tray_dimensions(columns: int, rows: int) -> tuple[int, int]:
    return (
        ROW_HEADER_WIDTH + columns * CELL_SIZE,
        rows * CELL_SIZE + COLUMN_HEADER_HEIGHT,
    )


def _tray_origin(columns: int, rows: int) -> tuple[float, float]:
    width, height = _tray_dimensions(columns, rows)
    return -width / 2, -height / 2


def _well_key(row_index: int, column_index: int) -> str:
    return f"{_position_to_letter(row_index + 1)}{column_index + 1}"


def _well_center(
    row_index: int,
    column_index: int,
    columns: int,
    rows: int,
    y_offset: float = 0,
) -> tuple[float, float]:
    left, top = _tray_origin(columns, rows)
    return (
        left + ROW_HEADER_WIDTH + column_index * CELL_SIZE + CELL_SIZE / 2,
        top + row_index * CELL_SIZE + (CELL_SIZE - y_offset) / 2,
    )


def _heat_port_position(columns: int, rows: int) -> tuple[float, float]:
    width, _ = _tray_dimensions(columns, rows)
    return width / 2 + HEAT_PORT_OFFSET, 0.0


@dataclass
class VialData(VesselComponentData):
    column: int = 3
    row: int = 2
    top_access: int = 1
    bottom_access: int = 0

    @property
    def is_array(self) -> bool:
        return self.column != 1 or self.row != 1

    @override
    def internal_structure(self) -> None:
        if not self.is_array:
            super().internal_structure()
            return

        self.port_pairs = []
        self.ports_by_number = {}
        self.internal_edges = {}
        self.internal_inventories = {}

        atmo_bc = None
        if not self.pressure_access:
            atmo_bc = PortBoundaryCondition(
                kind=BoundaryConditionKind.PRESSURE,
                value=float(ATMOSPHERE_PRESSURE_PA),
            )

        port_number = 1
        for row_index in range(self.row):
            for column_index in range(self.column):
                inventory_key = _well_key(row_index, column_index)
                self.ports_by_number[port_number] = Port(
                    number=port_number,
                    component=self.name,
                    relative_position=_well_center(
                        row_index,
                        column_index,
                        self.column,
                        self.row,
                        y_offset=CELL_SIZE / 2,
                    ),
                    category=ConnectionType.MOVEMENT,
                    access=PortAccess.BOTTOM,
                    boundary=atmo_bc,
                    show_in_graph=True,
                )
                self.port_pairs.append((port_number,))
                self.internal_edges[(port_number, inventory_key)] = InternalEdge(
                    origin_port=port_number,
                    destination_port=inventory_key,
                    role=InternalEdgeRole.JUNCTION,
                )
                self.internal_inventories[inventory_key] = InventoryNode(
                    gas_content=VolumeContentBase(volume=self.capacity_value),
                    liq_content=VolumeContentBase(
                        volume=0, phase_kind=PhaseKind.LIQUID
                    ),
                )
                port_number += 1

        if self.heat_exchange:
            self.ports_by_number[port_number] = Port(
                number=port_number,
                component=self.name,
                category=ConnectionType.HEAT,
                relative_position=_heat_port_position(self.column, self.row),
            )
            self.port_pairs.append((port_number,))


class VialMode(VesselMode):
    column: int = Field(
        default=3,
        ge=1,
        le=20,
        json_schema_extra={
            "group": GroupParameterCategory.PROPERTY.value,
            "editable": False,
            "creation_editable": True,
            "lock_reason": "Internal Chosen",
            "visible": True,
        },
    )
    row: int = Field(
        default=2,
        ge=1,
        le=20,
        json_schema_extra={
            "group": GroupParameterCategory.PROPERTY.value,
            "editable": False,
            "creation_editable": True,
            "lock_reason": "Internal Chosen",
            "visible": True,
        },
    )
    top_access: int = Field(
        default=1,
        json_schema_extra={
            "visible": False,
        },
    )
    bottom_access: int = Field(
        default=0,
        json_schema_extra={
            "visible": False,
        },
    )
    diameter: Annotated[ChemUnitQuantity, ChemQuantityValidator("m")] = Field(
        default=ChemUnitQuantity("0.01 m"),
        title="Diameter",
        description="Diameter of the component.",
        json_schema_extra={
            "group": GroupParameterCategory.PROPERTY.value,
        },
    )
