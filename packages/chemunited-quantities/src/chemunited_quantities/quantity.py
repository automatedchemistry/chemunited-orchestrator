import re

from pint import Quantity, UnitRegistry
from pydantic_pint import PydanticPintQuantity

ureg: UnitRegistry = UnitRegistry(autoconvert_offset_to_baseunit=True)

_QUANTITY_LITERAL = re.compile(
    r"^\s*"
    r"(?P<magnitude>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"
    r"\s+"
    r"(?P<unit>.+?)"
    r"\s*$"
)
_CELSIUS_ALIASES = {
    "degC": "degC",
    "\N{DEGREE SIGN}C": "degC",
    "degree_Celsius": "degC",
    "celsius": "degC",
}


def _parse_quantity_string(value: str) -> Quantity:
    """Parse a quantity string without multiplying offset temperature units."""
    match = _QUANTITY_LITERAL.fullmatch(value)
    if match is not None:
        magnitude = float(match.group("magnitude"))
        unit = match.group("unit").strip()
        unit = _CELSIUS_ALIASES.get(unit, unit)
        try:
            return ureg.Quantity(magnitude, unit)
        except Exception:  # nosec B110 - falls through to pint's own parser below
            pass
    return ureg(value)


# Curated lab-friendly units keyed by frozenset of (dimension, exponent) tuples.
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
    # Rotational speed: revolutions per minute, dimensionally [time]^-1
    (frozenset({("[time]", -1)}), ["rpm"]),
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
            valid: list[str] = []
            for unit in units:
                try:
                    ureg(unit)
                    valid.append(unit)
                except Exception:  # nosec B110 - skip curated units this registry doesn't recognize
                    pass
            return valid

    try:
        compatible_units = ureg.get_compatible_units(dimensions)
        canonical_unit = next(iter(compatible_units), None)
        if canonical_unit is None:
            return []
        q = ureg.Quantity(1, canonical_unit)
        return [str(q.units)]
    except Exception:
        return []


class ChemUnitQuantity(ureg.Quantity):  # type: ignore[name-defined]

    # ----------- Construction Helpers -----------

    @classmethod
    def parse(cls, v: object) -> "ChemUnitQuantity":
        if isinstance(v, Quantity):
            return cls(v.magnitude, str(v.units))
        if isinstance(v, str):
            q = _parse_quantity_string(v)
            return cls(q.magnitude, q.units)
        if isinstance(v, (int, float)):
            raise ValueError("Numeric values require a unit")
        raise ValueError(f"Unsupported type: {type(v)}")

    @staticmethod
    def from_any(v: object, default_unit: object | None = None) -> "ChemUnitQuantity":
        """
        Parse from:
        - pint.Quantity
        - string ("5 ml")
        - bare number + default_unit
        """
        if isinstance(v, ChemUnitQuantity):
            return v

        if isinstance(v, Quantity):
            return ChemUnitQuantity(v.magnitude, str(v.units))

        if isinstance(v, str):
            q = _parse_quantity_string(v)
            return ChemUnitQuantity(q.magnitude, q.units)

        if isinstance(v, (int, float)):
            if default_unit is None:
                raise ValueError("Numeric input requires a unit.")
            return ChemUnitQuantity(v, default_unit)

        raise TypeError(f"Cannot convert {v!r} to ChemUnitQuantity.")

    def __new__(cls, value, unit=None) -> "ChemUnitQuantity":
        # Case 1: string "5 ml"
        if isinstance(value, str) and unit is None:
            q = _parse_quantity_string(value)
            return super().__new__(cls, q.magnitude, q.units)  # type: ignore[no-any-return]

        # Case 2: magnitude + unit
        if unit is not None:
            return super().__new__(cls, value, unit)  # type: ignore[no-any-return]

        # Case 3: use pint.Quantity as input
        if isinstance(value, Quantity):
            return super().__new__(cls, value.magnitude, str(value.units))  # type: ignore[no-any-return]

        raise TypeError(f"Invalid input for ChemUnitQuantity: {value!r}, unit={unit!r}")

    # ----------- ADDITION (a + b) -----------

    def __add__(self, other: object) -> "ChemUnitQuantity":
        other_q = self.from_any(other, default_unit=self.units)
        result = super().__add__(other_q)
        return ChemUnitQuantity(result.magnitude, result.units)

    __radd__ = __add__

    # ----------- SUBTRACTION (a - b) -----------

    def __sub__(self, other: object) -> "ChemUnitQuantity":
        other_q = self.from_any(other, default_unit=self.units)
        result = super().__sub__(other_q)
        return ChemUnitQuantity(result.magnitude, result.units)

    def __rsub__(self, other: object) -> "ChemUnitQuantity":
        other_q = self.from_any(other, default_unit=self.units)
        result = other_q.__sub__(self)
        return ChemUnitQuantity(result.magnitude, result.units)

    # ----------- MULTIPLICATION (a * b) -----------

    def __mul__(self, other: object) -> "ChemUnitQuantity":
        if isinstance(other, (int, float)):
            result = super().__mul__(other)
            return ChemUnitQuantity(result.magnitude, result.units)

        other_q = self.from_any(other)
        result = super().__mul__(other_q)
        return ChemUnitQuantity(result.magnitude, result.units)

    __rmul__ = __mul__

    # ----------- DIVISION (a / b) -----------

    def __truediv__(self, other: object) -> "ChemUnitQuantity":
        if isinstance(other, (int, float)):
            result = super().__truediv__(other)
            return ChemUnitQuantity(result.magnitude, result.units)

        other_q = self.from_any(other)
        result = super().__truediv__(other_q)
        return ChemUnitQuantity(result.magnitude, result.units)

    def __rtruediv__(self, other: object) -> "ChemUnitQuantity":
        other_q = self.from_any(other)
        result = other_q.__truediv__(self)
        return ChemUnitQuantity(result.magnitude, result.units)

    # ----------- PRETTY PRINT -----------

    def __repr__(self) -> str:
        return f"<ChemUnitQuantity({self.magnitude}, '{self.units}')>"


class ChemQuantityValidator(PydanticPintQuantity):

    def __init__(self, _arg: str, **kwargs) -> None:
        kwargs.update(strict=False, ser_mode="str", ureg=ureg)
        super().__init__(_arg, **kwargs)

    def validate(self, *args, **kwargs) -> ChemUnitQuantity:
        if args:
            value = args[0]
            if isinstance(value, str):
                args = (_parse_quantity_string(value), *args[1:])
            elif isinstance(value, dict) and "magnitude" in value:
                unit = str(value.get("units", ""))
                quantity = _parse_quantity_string(
                    f"{value['magnitude']} {unit}".strip()
                )
                args = (quantity, *args[1:])
        v = super().validate(*args, **kwargs)
        return ChemUnitQuantity(v)

    def serialize(self, *args, **kwargs) -> dict | str | ChemUnitQuantity:
        v = super().serialize(*args, **kwargs)
        if isinstance(v, (dict, str)):
            return v
        return ChemUnitQuantity(v)
