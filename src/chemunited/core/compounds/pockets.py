from dataclasses import dataclass, field

from chemunited_core.common.constant import (
    AMBIENT_TEMPERATURE_K,
    ATMOSPHERE_PRESSURE_PA,
)
from chemunited_core.common.enums import PhaseKind


@dataclass(slots=True)
class VolumeContentBase:
    """A discrete volume of matter in a single phase state.

    Represents a well-mixed region holding a chemical mixture at uniform
    pressure and temperature, tracking species amounts in moles.

    Attributes:
        phase_kind: Thermodynamic phase of the contents (e.g. liquid, gas).
        volume: Volume of the pocket in cubic metres.
        species_moles: Mapping of species identifier to amount in moles.
        pressure: Absolute pressure in Pascals (default: 1 atm).
        temperature: Temperature in Kelvin (default: 298.15 K).
    """

    phase_kind: PhaseKind = PhaseKind.GAS
    volume: float = 0  # m³, geometric volume
    initial_species: dict[str, float] = field(default_factory=dict)
    initial_pressure: float = ATMOSPHERE_PRESSURE_PA
    initial_temperature: float = AMBIENT_TEMPERATURE_K
