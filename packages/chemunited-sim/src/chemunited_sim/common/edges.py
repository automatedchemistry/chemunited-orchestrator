"""Shared hydraulic-edge state predicates."""

from __future__ import annotations

from typing import TYPE_CHECKING

from chemunited_core.common.constant import R_MAX_HYDRAULIC

if TYPE_CHECKING:
    from ..adapter.models import HydraulicEdge


def is_hydraulically_closed(edge: HydraulicEdge) -> bool:
    """Return whether *edge* carries the established hard-closed marker."""
    return (
        edge.resistance_override is not None
        and edge.resistance_override >= R_MAX_HYDRAULIC / 2.0
    )
