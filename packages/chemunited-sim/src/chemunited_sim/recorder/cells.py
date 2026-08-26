"""Cell-definition builder for the recorder module.

Slices every TRANSPORT-role edge in a HydraulicGraph into fixed-length cells
for spatial recording.  JUNCTION and BPR edges (zero diameter) are excluded.
"""

from __future__ import annotations

import math

from chemunited_core.components.enums import InternalEdgeRole

from ..adapter.models import HydraulicGraph
from ..common.constant import RECORDER_CELL_LENGTH_M
from .models import CellDefinition


def build_cell_definitions(
    graph: HydraulicGraph,
    cell_length_m: float = RECORDER_CELL_LENGTH_M,
) -> list[CellDefinition]:
    """Slice every eligible TRANSPORT edge into fixed-length cells.

    Edges are eligible when ``role == TRANSPORT``, ``length > 0``, and
    ``diameter > 0``.  BPR edges (``diameter == 0``) are excluded because
    they model a valve with no physical volume.

    The last cell in each edge absorbs any remainder so the full edge length
    is always covered.  Minimum one cell per edge.

    Cells are ordered first by ``edge_id`` (lexicographic), then by
    ``cell_index`` ascending.

    Parameters
    ----------
    graph:
        Compiled hydraulic graph.
    cell_length_m:
        Nominal cell length in metres.  Defaults to
        :data:`~chemunited_sim.common.constant.RECORDER_CELL_LENGTH_M`.

    Returns
    -------
    list[CellDefinition]
        All cell descriptors for the graph.
    """
    cells: list[CellDefinition] = []

    for edge_id in sorted(graph.edges):
        edge = graph.edges[edge_id]
        if edge.role != InternalEdgeRole.TRANSPORT:
            continue
        if edge.length <= 0.0 or edge.diameter <= 0.0:
            continue

        n_cells = max(1, math.ceil(edge.length / cell_length_m))

        for i in range(n_cells):
            position_m = i * cell_length_m
            if i < n_cells - 1:
                length_m = cell_length_m
            else:
                # Last cell absorbs remainder
                length_m = edge.length - (n_cells - 1) * cell_length_m

            cells.append(
                CellDefinition(
                    edge_id=edge_id,
                    cell_index=i,
                    position_m=position_m,
                    length_m=length_m,
                )
            )

    return cells
