from __future__ import annotations

from pint import UnitRegistry

# Curated lab-friendly units keyed by frozenset of (dimension, exponent) tuples.
# Covers the dimensions used in chemunited-core field definitions.
_CURATED: list[tuple[frozenset, list[str]]] = [
    # Volume:  [length]^3
    (frozenset({("[length]", 3)}), ["ml", "ul", "L", "cl", "dl"]),
    # Length:  [length]^1
    (frozenset({("[length]", 1)}), ["mm", "cm", "m", "um", "nm", "inch"]),
    # Flow rate:  [length]^3 / [time]
    (
        frozenset({("[length]", 3), ("[time]", -1)}),
        ["ml/min", "ul/min", "ml/s", "L/min", "ul/s", "L/h"],
    ),
    # Pressure:  [mass] / ([length] * [time]^2)
    (
        frozenset({("[mass]", 1), ("[length]", -1), ("[time]", -2)}),
        ["bar", "mbar", "Pa", "kPa", "MPa", "psi"],
    ),
    # Time:  [time]^1
    (frozenset({("[time]", 1)}), ["s", "min", "h", "ms"]),
    # Temperature:  [temperature]^1
    (frozenset({("[temperature]", 1)}), ["degC", "kelvin", "degF"]),
    # Mass:  [mass]^1
    (frozenset({("[mass]", 1)}), ["g", "mg", "kg", "ug"]),
    # Molar mass: [mass] / [substance]
    (frozenset({("[mass]", 1), ("[substance]", -1)}), ["g/mol", "kg/mol"]),
    # Heat Transfer Coefficient: [mass] / ([time]^3 * [temperature])
    (
        frozenset(
            {
                ("[mass]", 1),
                ("[time]", -3),
                ("[temperature]", -1),
            }
        ),
        ["W/(m^2*K)", "kW/(m^2*K)", "BTU/(hr*ft^2*delta_degF)"],
    ),
    # Molar heat capacity: [energy] / ([substance] * [temperature])
    (
        frozenset(
            {
                ("[mass]", 1),
                ("[length]", 2),
                ("[time]", -2),
                ("[substance]", -1),
                ("[temperature]", -1),
            }
        ),
        ["J/(mol*K)", "kJ/(mol*K)", "cal/(mol*K)"],
    ),
    # Density: [mass] / [length]^3
    (
        frozenset({("[mass]", 1), ("[length]", -3)}),
        ["kg/m^3", "g/cm^3", "g/ml"],
    ),
    # Concentration (amount/volume):  [substance] / [length]^3
    (
        frozenset({("[substance]", 1), ("[length]", -3)}),
        ["mol/L", "mmol/L", "umol/L", "mol/ml"],
    ),
]


def units_for_dimension(dimensions, ureg: UnitRegistry) -> list[str]:
    """Return a curated list of unit strings compatible with *dimensions*.

    *dimensions* is a pint ``UnitsContainer`` (e.g. from
    ``ChemQuantityValidator.dimensions``).  If no curated match is found,
    falls back to returning the default unit derived from *dimensions*.
    """
    if dimensions is None:
        return []

    key = frozenset((dim, exp) for dim, exp in dimensions.items())

    for curated_key, units in _CURATED:
        if key == curated_key:
            # Validate all strings are parseable by ureg; drop any that are not.
            valid: list[str] = []
            for u in units:
                try:
                    ureg(u)
                    valid.append(u)
                except Exception:
                    pass
            return valid

    # Fallback: return the canonical unit for the dimensionality
    try:
        compatible_units = ureg.get_compatible_units(dimensions)
        canonical_unit = next(iter(compatible_units), None)
        if canonical_unit is None:
            return []
        q = ureg.Quantity(1, canonical_unit)
        return [str(q.units)]
    except Exception:
        return []
