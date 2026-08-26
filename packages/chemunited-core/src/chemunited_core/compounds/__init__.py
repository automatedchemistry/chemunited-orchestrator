"""chemunited-core compounds module.

Provides chemical substance definitions and the project-wide compound registry.

    VolumeContentBase  — initial condition descriptor for a volume of matter.
                         Used in InventoryNode to declare starting phase state.
    ChemicalEntity     — static descriptor for a pure chemical substance.
                         Stores Cp, density, and molecular weight.
    Compounds          — registry class for chemical entities.
    COMPOUNDS          — module-level singleton registry; populated at project
                         load time by the GUI, read by chemunited-sim.
"""

from .entity import ChemicalEntity
from .pockets import VolumeContentBase
from .registry import COMPOUNDS, Compounds

__all__ = [
    "ChemicalEntity",
    "COMPOUNDS",
    "Compounds",
    "VolumeContentBase",
]
