from dataclasses import dataclass

from pydantic import Field, field_validator
from typing_extensions import override

from chemunited_core.common.constant import ATMOSPHERE_PRESSURE_PA, PATTERN_DIMENSION
from chemunited_core.common.enums import ConnectionType, GroupParameterCategory
from chemunited_core.components import (
    ComponentData,
    ComponentMode,
    PutResult,
)
from chemunited_core.components.enums import BoundaryConditionKind, InternalEdgeRole
from chemunited_core.components.internals import (
    InternalEdge,
    Port,
    PortBoundaryCondition,
)

GANTRY_PORTS_PER_ROW = 20


class Gantry1DMode(ComponentMode):
    position_x: str = Field(
        default="1",
        title="Actual gantry position",
        description="The actual gantry position can be '1', '2', and so on. ",
        examples=["1", "2", "3"],
        json_schema_extra={"group": GroupParameterCategory.STATUS.value},
    )
    connections_number: int = Field(
        default=40,
        gt=0,
        title="Movement connections numbers",
        description=(
            "The number of movement connections in the gantry that "
            "need to be connected to the others components."
        ),
        json_schema_extra={
            "group": GroupParameterCategory.PROPERTY.value,
            "editable": False,
            "creation_editable": True,
        },
    )

    @field_validator("position_x")
    def validate_x(cls, value: str) -> str:
        if not value.isdigit() or int(value) <= 0:
            raise ValueError(
                "position_x must be a digit greater than 0 (e.g. '1', '2', ...)."
            )
        return value


class Gantry3DMode(Gantry1DMode):
    position_y: str = Field(
        default="A",
        title="Actual position at y axis",
        description="The actual position on the y-axis can be 'A', 'B', and so on. ",
        examples=["A", "B", "C"],
        json_schema_extra={"group": GroupParameterCategory.STATUS.value},
    )
    position_z: str = Field(
        default="UP",
        title="Actual position at z axis",
        description="The actual position on the y-axis can be 'UP', and 'DOWN'. ",
        examples=["UP", "DOWN"],
        json_schema_extra={
            "group": GroupParameterCategory.STATUS.value,
            "Options": ["UP", "DOWN"],
        },
    )

    @field_validator("position_y")
    def validate_y(cls, value: str) -> str:
        if not (len(value) == 1 and value.isalpha() and value.isupper()):
            raise ValueError(
                "position_y must be a single uppercase letter (e.g. 'A', 'B', ...)."
            )
        return value

    @field_validator("position_z")
    def validate_z(cls, value: str) -> str:
        if value not in {"UP", "DOWN"}:
            raise ValueError("position_z must be either 'UP' or 'DOWN'.")
        return value


@dataclass
class Gantry1DData(ComponentData):
    position_x: str = "1"
    connections_number: int = 40

    @property
    def selected_port(self) -> int | None:
        try:
            port_number = int(self.position_x) + 1
        except ValueError:
            return None
        if port_number < 2:
            return None
        if port_number >= 2 + self.connections_number:
            return None
        return port_number

    @override
    def internal_structure(self) -> None:
        self.port_pairs = [(1, i + 2) for i in range(self.connections_number)]
        self.ports_by_number = {
            1: Port(
                number=1,
                component=self.name,
                relative_position=(0, -1.05 * PATTERN_DIMENSION),
            )
        }
        self.internal_edges = {}
        factor_y: float = 1
        factor_x = 0
        for i in range(self.connections_number):
            if i % GANTRY_PORTS_PER_ROW == 0:
                factor_x = 0
                factor_y += 0.4
            self.ports_by_number[i + 2] = Port(
                number=i + 2,
                component=self.name,
                category=ConnectionType.MOVEMENT,
                relative_position=(
                    factor_x - 2 * PATTERN_DIMENSION,
                    factor_y * PATTERN_DIMENSION + 10,
                ),
                show_in_graph=True,
            )
            self.internal_edges[(1, i + 2)] = InternalEdge(
                origin_port=1,
                destination_port=i + 2,
                role=InternalEdgeRole.JUNCTION,
            )
            factor_x += 14
        self.internal_inventories = {}
        self.sync_internal_state()

    @override
    def sync_internal_state(self) -> None:
        selected_port = self.selected_port

        for (_, destination_port), edge in self.internal_edges.items():
            if destination_port == selected_port:
                edge.open()
            else:
                edge.close()

        head_port = self.ports_by_number[1]
        if selected_port is None:
            head_port.boundary = PortBoundaryCondition(
                kind=BoundaryConditionKind.PRESSURE,
                value=float(ATMOSPHERE_PRESSURE_PA),
            )
        else:
            head_port.boundary = None

    @override
    def apply(self, command: str, **kwargs) -> PutResult:
        if command in {"position", "set_x_position"}:
            self.position_x = str(kwargs["position"])
        else:
            return PutResult()

        self.sync_internal_state()
        return PutResult()


@dataclass
class Gantry3DData(Gantry1DData):
    position_y: str = "A"
    position_z: str = "UP"

    @property
    @override
    def selected_port(self) -> int | None:
        if len(self.position_y) != 1:
            return None
        try:
            column_index = int(self.position_x) - 1
        except ValueError:
            return None
        row_index = ord(self.position_y) - ord("A")
        port_number = 2 + row_index * GANTRY_PORTS_PER_ROW + column_index
        if row_index < 0 or column_index < 0:
            return None
        if port_number >= 2 + self.connections_number:
            return None
        return port_number

    @override
    def sync_internal_state(self) -> None:
        selected_port = self.selected_port if self.position_z == "DOWN" else None

        for (_, destination_port), edge in self.internal_edges.items():
            if destination_port == selected_port:
                edge.open()
            else:
                edge.close()

        head_port = self.ports_by_number[1]
        if selected_port is None:
            head_port.boundary = PortBoundaryCondition(
                kind=BoundaryConditionKind.PRESSURE,
                value=float(ATMOSPHERE_PRESSURE_PA),
            )
        else:
            head_port.boundary = None

    @override
    def apply(self, command: str, **kwargs) -> PutResult:
        if command == "set_x_position":
            self.position_x = str(kwargs["position"])
        elif command == "set_y_position":
            self.position_y = str(kwargs["position"]).upper()
        elif command == "set_z_position":
            self.position_z = str(kwargs["position"])
        else:
            return PutResult()

        self.sync_internal_state()
        return PutResult()
