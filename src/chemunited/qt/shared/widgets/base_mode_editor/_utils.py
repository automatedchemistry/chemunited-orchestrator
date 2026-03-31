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
    (frozenset({("[length]", 3), ("[time]", -1)}), ["ml/min", "ul/min", "ml/s", "L/min", "ul/s", "L/h"]),
    # Pressure:  [mass] / ([length] * [time]^2)
    (frozenset({("[mass]", 1), ("[length]", -1), ("[time]", -2)}), ["bar", "mbar", "Pa", "kPa", "MPa", "psi"]),
    # Time:  [time]^1
    (frozenset({("[time]", 1)}), ["s", "min", "h", "ms"]),
    # Temperature:  [temperature]^1
    (frozenset({("[temperature]", 1)}), ["degC", "kelvin", "degF"]),
    # Mass:  [mass]^1
    (frozenset({("[mass]", 1)}), ["g", "mg", "kg", "ug"]),
    # Concentration (amount/volume):  [substance] / [length]^3
    (frozenset({("[substance]", 1), ("[length]", -3)}), ["mol/L", "mmol/L", "umol/L", "mol/ml"]),
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
        q = ureg.Quantity(1, ureg.get_compatible_units(dimensions).pop())
        return [str(q.units)]
    except Exception:
        return []
