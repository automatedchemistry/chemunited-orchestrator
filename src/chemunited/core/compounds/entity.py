"""Chemical entity definition for the chemunited-core compounds module.

Defines ChemicalEntity — a static descriptor for a pure chemical substance.
Stores user-provided physical properties and provides derived quantities
computed on demand using simplified ideal-gas and ideal-mixture assumptions.

Used by:
    - GUI (Setup Manager)  to populate compound pickers and validate species names.
    - chemunited-sim       to retrieve Cp, density, and molar volume during
                           heat balance and pocket property calculations.

All physical quantities in SI units unless noted otherwise.
"""

from dataclasses import dataclass

IDEAL_GAS_CONSTANT = 8.314  # J/(mol·K)


@dataclass
class ChemicalEntity:
    """Static descriptor for a pure chemical substance.

    Stores user-provided physical properties. Phase-specific fields
    (cp_liquid, cp_gas, density_liquid) are None when the phase is not
    relevant for the compound — no phase change is assumed during simulation.

    Attributes:
        name:            Unique identifier used as the key in species_moles dicts.
        molecular_weight: Molar mass in g/mol.
        cp_liquid:       Molar heat capacity of the liquid phase in J/(mol·K).
                         None if the compound is never liquid in this simulation.
        cp_gas:          Molar heat capacity of the gas phase in J/(mol·K).
                         None if the compound is never gaseous in this simulation.
        density_liquid:  Liquid phase density in kg/m³.
                         None if the compound is never liquid in this simulation.
    """

    name: str
    molecular_weight: float          # g/mol
    cp_liquid: float | None = None   # J/(mol·K)
    cp_gas: float | None = None      # J/(mol·K)
    density_liquid: float | None = None  # kg/m³

    # ── Derived quantities ────────────────────────────────────────────────

    def molar_volume_gas(self, temperature: float, pressure: float) -> float:
        """Ideal-gas molar volume in m³/mol.

        Args:
            temperature: Temperature in K.
            pressure:    Absolute pressure in Pa.

        Returns:
            Molar volume in m³/mol.
        """
        return IDEAL_GAS_CONSTANT * temperature / pressure

    def molar_volume_liquid(self) -> float:
        """Liquid molar volume in m³/mol derived from density.

        Returns:
            Molar volume in m³/mol.

        Raises:
            ValueError: If density_liquid is not defined for this compound.
        """
        if self.density_liquid is None:
            raise ValueError(
                f"density_liquid is not defined for compound '{self.name}'."
            )
        return (self.molecular_weight * 1e-3) / self.density_liquid

    def cp(self, phase: str) -> float:
        """Heat capacity for the requested phase in J/(mol·K).

        Args:
            phase: Phase identifier — 'liquid' or 'gas'.

        Returns:
            Molar heat capacity in J/(mol·K).

        Raises:
            ValueError: If the requested phase Cp is not defined.
        """
        if phase == "liquid":
            if self.cp_liquid is None:
                raise ValueError(
                    f"cp_liquid is not defined for compound '{self.name}'."
                )
            return self.cp_liquid
        if phase == "gas":
            if self.cp_gas is None:
                raise ValueError(
                    f"cp_gas is not defined for compound '{self.name}'."
                )
            return self.cp_gas
        raise ValueError(f"Unknown phase '{phase}'. Expected 'liquid' or 'gas'.")
