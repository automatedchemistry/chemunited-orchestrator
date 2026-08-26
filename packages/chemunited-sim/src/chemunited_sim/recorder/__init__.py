"""Recorder module — SQLite-backed simulation state persistence."""

from .cells import build_cell_definitions
from .models import CellDefinition
from .writer import Recorder, RecorderWriteError

__all__ = [
    "CellDefinition",
    "build_cell_definitions",
    "Recorder",
    "RecorderWriteError",
]
