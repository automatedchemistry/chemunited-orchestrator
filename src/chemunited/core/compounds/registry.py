"""Global compound registry for chemunited-core.

Provides the Compounds registry class and the COMPOUNDS singleton that acts
as the project-wide catalogue of chemical entities.

The registry is populated at project load time by the GUI (Setup Manager)
and read by chemunited-sim during simulation to retrieve physical properties.

Usage:
    from chemunited_core.compounds import COMPOUNDS

    # Register a compound (done at project load time by the GUI)
    COMPOUNDS.register(ChemicalEntity(
        name="water",
        molecular_weight=18.015,
        cp_liquid=75.3,
        cp_gas=33.6,
        density_liquid=997.0,
    ))

    # Read a compound (done by sim layer or GUI property panels)
    water = COMPOUNDS["water"]
    print(water.cp_liquid)

    # Reset between projects
    COMPOUNDS.clear()
"""

from .entity import ChemicalEntity


class Compounds:
    """Project-wide registry of chemical entities.

    Acts as a named catalogue of ChemicalEntity objects available in the
    current project. Populated by the GUI at project load time and read
    by chemunited-sim during simulation.

    Supports dict-style access: COMPOUNDS["water"] returns the entity.
    Supports membership test: "water" in COMPOUNDS.

    Must be reset via clear() when a new project is loaded to prevent
    stale compounds from a previous project persisting in memory.
    """

    def __init__(self) -> None:
        self._compounds: dict[str, ChemicalEntity] = {}

    def register(self, entity: ChemicalEntity) -> None:
        """Add a chemical entity to the registry.

        Args:
            entity: The ChemicalEntity to register.
                    Its name is used as the registry key.
        """
        self._compounds[entity.name] = entity

    def clear(self) -> None:
        """Remove all compounds from the registry.

        Call this when loading a new project to avoid stale data.
        """
        self._compounds.clear()

    def __getitem__(self, name: str) -> ChemicalEntity:
        """Retrieve a compound by name.

        Args:
            name: The compound identifier (matches ChemicalEntity.name).

        Returns:
            The corresponding ChemicalEntity.

        Raises:
            KeyError: If the compound is not registered.
        """
        try:
            return self._compounds[name]
        except KeyError:
            raise KeyError(
                f"Compound '{name}' is not registered. "
                f"Available compounds: {self.names}"
            )

    def __contains__(self, name: str) -> bool:
        """Check if a compound is registered by name."""
        return name in self._compounds

    def __len__(self) -> int:
        """Return the number of registered compounds."""
        return len(self._compounds)

    def __repr__(self) -> str:
        return f"Compounds({self.names})"

    @property
    def names(self) -> list[str]:
        """List of all registered compound names."""
        return list(self._compounds.keys())

    @property
    def entities(self) -> list[ChemicalEntity]:
        """List of all registered ChemicalEntity objects."""
        return list(self._compounds.values())


# ── Module-level singleton ────────────────────────────────────────────────────

COMPOUNDS = Compounds()
"""Project-wide compound registry singleton.

Populated at project load time by the GUI. Read by chemunited-sim during
simulation. Reset via COMPOUNDS.clear() when a new project is loaded.
"""
