"""Transport layer data structures for chemunited-sim.

``Pocket``        — an immutable parcel of fluid moving through an edge.
``TransportState``— the FIFO queues for all transport edges at one instant.
``TransportResult``— the output of one :func:`advance` call.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from chemunited_core.common.enums import PhaseKind


@dataclass(frozen=True, slots=True)
class Pocket:
    """An immutable parcel of fluid inside a transport edge.

    Pockets are the fundamental unit of transport.  Each edge holds an
    ordered :class:`collections.deque` of Pockets that advances one step at
    a time according to the signed volumetric flow from the hydraulic solve.

    Attributes
    ----------
    phase_kind:
        ``LIQUID`` or ``GAS``.  Different phases never merge during transport.
    volume:
        Geometric volume of this parcel in m³.
    species_moles:
        Chemical composition as ``{species_id: moles}``.  Empty dict means
        pure carrier fluid (e.g. initial air fill).  Do NOT mutate after
        construction — the dataclass is frozen but the dict is not.
    temperature:
        Temperature in K.
    pressure:
        Local pressure in Pa at the time of creation.
    """

    phase_kind: PhaseKind
    volume: float
    species_moles: dict[str, float]
    temperature: float
    pressure: float


@dataclass
class TransportState:
    """FIFO pocket queues for every transport edge in the hydraulic graph.

    Attributes
    ----------
    edge_queues:
        Mapping from ``edge_id`` to the ordered queue of :class:`Pocket`
        objects currently inside that edge.

        Deque ordering convention — **fixed to graph orientation**,
        regardless of current flow direction:

        * ``deque[0]`` (left) = pocket closest to the **destination** node.
        * ``deque[-1]`` (right) = pocket closest to the **origin** node.

        When flow is positive (origin → destination) the left pocket exits
        next (``popleft``).  When flow reverses, the right pocket exits next
        (``pop``).
    """

    edge_queues: dict[str, deque[Pocket]]


@dataclass(frozen=True)
class TransportResult:
    """Output of one :func:`~chemunited_sim.transport.engine.advance` call.

    Attributes
    ----------
    next_state:
        Updated :class:`TransportState` to pass to the next call.
    arrivals:
        Pockets that reached an inventory node this step, keyed by
        ``inventory_node_id`` (e.g. ``"vessel1.Inventory"``).
        Consumed by the inventory module's assimilate step.
    departures:
        Volume (m³) that left the inventory-connected end of each transport
        edge this step, keyed by ``edge_id``.
        One entry per edge whose inflow end neighbours an inventory node.
        Consumed by the inventory module's emit step to produce replacement
        pockets (one per port).
    """

    next_state: TransportState
    arrivals: dict[str, list[Pocket]]
    departures: dict[str, float]
