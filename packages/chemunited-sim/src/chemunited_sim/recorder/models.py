"""Recorder data structures for chemunited-sim."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CellDefinition:
    """Geometry descriptor for one fixed-length cell within a transport edge.

    Cells are ordered from the origin end of the edge (cell_index 0) toward
    the destination end.  The last cell in each edge absorbs any remainder so
    that the full edge length is always covered.

    Attributes
    ----------
    edge_id:
        The transport edge this cell belongs to.
    cell_index:
        Zero-based index within the edge (0 = origin end).
    position_m:
        Position of this cell's left (origin-side) face in metres, measured
        from the edge's origin node.
    length_m:
        Cell length in metres.
    """

    edge_id: str
    cell_index: int
    position_m: float
    length_m: float
