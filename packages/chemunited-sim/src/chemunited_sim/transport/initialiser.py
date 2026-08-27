"""Initial transport state builder for chemunited-sim.

Seeds TRANSPORT edges from their ``content`` list (set during graph compilation).
Each segment in ``content`` becomes one initial :class:`Pocket`.  JUNCTION-role
edges are excluded (lossless, no physical volume).
"""

from __future__ import annotations

from collections import deque

from chemunited_core.components.enums import InternalEdgeRole

from ..adapter.models import HydraulicGraph
from ..common.constant import MIN_POCKET_VOLUME
from .models import Pocket, TransportState


def build_initial_state(graph: HydraulicGraph) -> TransportState:
    """Create a :class:`TransportState` seeded from each edge's ``content`` list.

    Each entry in ``HydraulicEdge.content`` becomes one initial
    :class:`Pocket`.  Edges with an empty ``content`` list (e.g.
    zero-length edges) get an empty queue.

    Parameters
    ----------
    graph:
        The compiled hydraulic graph whose edges carry their initial content.

    Returns
    -------
    TransportState
        One entry per TRANSPORT edge in ``graph.edges``.
    """
    edge_queues: dict[str, deque[Pocket]] = {}

    for edge_id, edge in graph.edges.items():
        if edge.role != InternalEdgeRole.TRANSPORT:
            continue

        if not edge.content:
            edge_queues[edge_id] = deque()
            continue

        pockets = []
        for seg in edge.content:
            if seg.volume < MIN_POCKET_VOLUME:
                continue
            pockets.append(
                Pocket(
                    phase_kind=seg.phase_kind,
                    volume=seg.volume,
                    species_moles=dict(seg.initial_species),
                    temperature=seg.initial_temperature,
                    pressure=seg.initial_pressure,
                )
            )

        edge_queues[edge_id] = deque(pockets)

    return TransportState(edge_queues=edge_queues)
