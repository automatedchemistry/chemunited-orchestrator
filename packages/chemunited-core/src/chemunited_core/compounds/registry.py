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
        molecular_weight="18.015 g/mol",
        cp_liquid="75.3 J/(mol*K)",
        cp_gas="33.6 J/(mol*K)",
        density_liquid="997 kg/m^3",
    ))

    # Read a compound (done by sim layer or GUI property panels)
    water = COMPOUNDS["water"]
    print(water.cp_liquid)

    # Reset between projects
    COMPOUNDS.clear()
"""

from chemunited_core.common.enums import PhaseKind

from .entity import ChemicalEntity
from .pockets import VolumeContentBase

_AIR = ChemicalEntity(
    name="air",
    color_red=0,
    color_green=0,
    color_blue=0,
    color_alpha=0,
)
_AIR_SPECIES = "air"
_TRANSPARENT_COLOR = "#FFFFFF00"


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
        self._compounds: dict[str, ChemicalEntity] = {"air": _AIR}

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
        Built-in compounds (air) are restored automatically.
        """
        self._compounds.clear()
        self._compounds["air"] = _AIR

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

    def get_color(self, content: VolumeContentBase) -> str:
        """Return the display RGBA color for a volume content mixture."""
        if content.phase_kind == PhaseKind.GAS:
            return self._blend_colors(content.initial_species, opacity=0.5)
        if content.phase_kind == PhaseKind.LIQUID:
            return self._blend_colors(content.initial_species, opacity=1.0)

        raise ValueError(
            f"Unknown phase '{content.phase_kind}'. Expected 'liquid' or 'gas'."
        )

    def _blend_colors(self, species_moles: dict[str, float], opacity: float) -> str:
        """Blend colors of individual compounds based on their mole fractions.

        Args:
            species_moles: Mapping of species identifier to amount in moles.
            opacity: Desired opacity level (0.0 to 1.0) for the blended color.

        Returns:
            A hex color string for the blended color and opacity.
        """
        visible_species = {
            species: moles
            for species, moles in species_moles.items()
            if species != _AIR_SPECIES and species in self._compounds and moles > 0
        }
        total_moles = sum(visible_species.values())
        if total_moles == 0:
            return _TRANSPARENT_COLOR

        r_total, g_total, b_total = 0.0, 0.0, 0.0
        for species, moles in visible_species.items():
            entity = self._compounds[species]
            r, g, b = self._hex_to_rgb(entity.rgb_hex)
            fraction = moles / total_moles
            r_total += r * fraction
            g_total += g * fraction
            b_total += b * fraction

        r_blend = round(r_total)
        g_blend = round(g_total)
        b_blend = round(b_total)
        a_blend = round(opacity * 255)

        return f"#{r_blend:02X}{g_blend:02X}{b_blend:02X}{a_blend:02X}"

    def _hex_to_rgb(self, color: str) -> tuple[int, int, int]:
        """Parse a six- or eight-digit hex color into RGB channels."""
        if not color.startswith("#") or len(color) not in {7, 9}:
            raise ValueError(
                f"Invalid color '{color}'. Expected '#RRGGBB' or '#RRGGBBAA'."
            )

        return (
            int(color[1:3], 16),
            int(color[3:5], 16),
            int(color[5:7], 16),
        )


# ── Module-level singleton ────────────────────────────────────────────────────

COMPOUNDS = Compounds()
"""Project-wide compound registry singleton.

Populated at project load time by the GUI. Read by chemunited-sim during
simulation. Reset via COMPOUNDS.clear() when a new project is loaded.
"""
