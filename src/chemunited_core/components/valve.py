"""Rotary valve component — multi-position switching element.

Models any rotary valve (injection, distribution, multiposition) using a
geometric stator/rotor representation. All possible internal channels are
compiled into the subgraph at construction; only the channels corresponding
to the current rotor position are open (resistance computed from geometry).
All other channels are closed (resistance = R_MAX_HYDRAULIC).

GUI: stator_ports and rotor_ports define the valve geometry and are not
     user-editable after component creation.
Sim: sync_internal_state() re-derives active connections from the current
     rotor layout; the DigitalTwinAdapter reads InternalEdge.is_active to
     build the active hydraulic assembly each time step.
"""

from copy import copy
from dataclasses import dataclass, field
from typing import ClassVar, TypeAlias

import numpy as np
from pydantic import Field
from typing_extensions import override

from chemunited_core.common.constant import PATTERN_DIMENSION
from chemunited_core.components.component import ComponentData, ComponentMode
from chemunited_core.components.enums import ComponentType, InternalEdgeRole
from chemunited_core.components.internals import InternalEdge, Port

ValvePortRow: TypeAlias = tuple[int | None, ...]
ValvePortLayout: TypeAlias = list[ValvePortRow]

DEFAULT_STATOR_PORTS: ValvePortLayout = [(1, 2, 3, 4, 5, 6), (0,)]
DEFAULT_ROTOR_PORTS: ValvePortLayout = [(7, None, None, None, None, None), (7,)]


def _copy_port_layout(layout: ValvePortLayout) -> ValvePortLayout:
    return [tuple(row) for row in layout]


def rotate_rotor(
    rotor_ports: ValvePortLayout, clockwise: bool = True
) -> ValvePortLayout:
    rotor_ports_new = [(), rotor_ports[1]]
    if clockwise:
        rotor_ports_new[0] = (rotor_ports[0][-1],) + rotor_ports[0][:-1]
    else:
        rotor_ports_new[0] = rotor_ports[0][1:] + (rotor_ports[0][0],)
    return rotor_ports_new


def connection_from_rotor(
    stator_ports: ValvePortLayout,
    rotor_ports: ValvePortLayout,
) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    rotor_position: list[tuple[int, int]] = []
    connection: list[tuple[int, int]] = []
    rotor_variable = [element for element in rotor_ports[0]]

    for i, element in enumerate(rotor_variable):
        if element is None:
            continue

        for j, partner in enumerate(rotor_variable):
            if partner == element and j != i:
                rotor_variable[j] = None
                rotor_variable[i] = None
                rotor_position.append((i + 1, j + 1))

                origin_port = stator_ports[0][i]
                destination_port = stator_ports[0][j]
                if origin_port is not None and destination_port is not None:
                    connection.append((origin_port, destination_port))

                break

    rotor_variable = [element for element in rotor_ports[0]]
    if rotor_ports[1][0] is not None:
        for j, partner in enumerate(rotor_variable):
            if partner == rotor_ports[1][0]:
                rotor_position.append((0, j + 1))
                destination_port = stator_ports[0][j]
                if destination_port is not None:
                    connection.append((0, destination_port))
                break

    return rotor_position, connection


def possibles_connections_pairs(
    stator_ports: ValvePortLayout,
    rotor_ports: ValvePortLayout,
) -> list[tuple[int, int]]:
    points: list[tuple[int, int]] = []
    rotor_new = copy(rotor_ports)

    for _ in range(len(rotor_ports[0])):
        rotor_new = rotate_rotor(rotor_ports=rotor_new)
        _, connections = connection_from_rotor(
            stator_ports=stator_ports,
            rotor_ports=rotor_new,
        )
        points.extend(connections)

    return sorted(set(points))


def _port_numbers_from_stator(
    stator_ports: ValvePortLayout, rotor_ports: ValvePortLayout
) -> list[int]:
    numbers = {number for row in stator_ports for number in row if number is not None}
    if 0 in numbers and rotor_ports[1][0] is None:
        numbers.remove(0)
    return sorted(numbers)


class ValveMode(ComponentMode):
    """Valve geometry parameters — not editable after component creation.
    stator_ports — layout of external ports on the valve body.
    rotor_ports  — rotor channel layout used to derive active connections.
    """

    stator_ports: ValvePortLayout = Field(
        default_factory=lambda: _copy_port_layout(DEFAULT_STATOR_PORTS)
    )
    rotor_ports: ValvePortLayout = Field(
        default_factory=lambda: _copy_port_layout(DEFAULT_ROTOR_PORTS)
    )


@dataclass
class ValveComponentData(ComponentData):
    """Structural definition of a rotary valve.

    Derives all possible port connections geometrically from stator/rotor
    layouts. Active connections reflect the current rotor position.
    Switching is performed by calling sync_internal_state() after updating
    the rotor layout — the sim adapter calls this on each protocol switch command.
    """

    COMPONENT_TYPE = ComponentType.ELECTRONIC
    # Internally properties (It will be overwritten according to the valve topology)
    stator_ports: ValvePortLayout = field(
        default_factory=lambda: _copy_port_layout(DEFAULT_STATOR_PORTS)
    )
    rotor_ports: ValvePortLayout = field(
        default_factory=lambda: _copy_port_layout(DEFAULT_ROTOR_PORTS)
    )
    internal_radius = PATTERN_DIMENSION
    hub_ports: ClassVar[tuple[int, ...]] = ()

    @override
    def internal_structure(self) -> None:
        connections = possibles_connections_pairs(
            stator_ports=self.stator_ports,
            rotor_ports=self.rotor_ports,
        )
        valve_port_pairs: list[tuple[int, ...]] = [pair for pair in connections]
        self.port_pairs = valve_port_pairs
        self.ports_by_number = {
            number: Port(
                number=number,
                component=self.name,
                is_hub=number in self.hub_ports,
            )
            for number in _port_numbers_from_stator(self.stator_ports, self.rotor_ports)
        }
        self.internal_edges = {
            pair: InternalEdge(
                origin_port=pair[0],
                destination_port=pair[1],
                role=InternalEdgeRole.JUNCTION,
            ).close()
            for pair in connections
        }

        _, active_connections = connection_from_rotor(
            stator_ports=self.stator_ports,
            rotor_ports=self.rotor_ports,
        )
        for pair in active_connections:
            self.internal_edges[pair].open()

        # Correct of the position of the ports
        n = len(self.stator_ports[0])
        angles_effective = np.arange(-np.pi / 2, 3 * np.pi / 2, 2 * np.pi / n)
        for i, c in enumerate(self.stator_ports[0]):
            if c is not None:
                phi = angles_effective[i]
                self.ports_by_number[c].relative_position = (
                    self.internal_radius * np.cos(phi),
                    self.internal_radius * np.sin(phi),
                )

    @override
    def sync_internal_state(self) -> None:
        for edge in self.internal_edges.values():
            edge.close()

        _, active_connections = connection_from_rotor(
            stator_ports=self.stator_ports,
            rotor_ports=self.rotor_ports,
        )
        for pair in active_connections:
            self.internal_edges[pair].open()
