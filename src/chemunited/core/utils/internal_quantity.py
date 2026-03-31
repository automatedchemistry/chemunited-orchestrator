from pint import Quantity, UnitRegistry
from pydantic_pint import PydanticPintQuantity

ureg: UnitRegistry = UnitRegistry()


class ChemUnitQuantity(Quantity):

    # ----------- Construction Helpers -----------

    @classmethod
    def parse(cls, v):
        if isinstance(v, Quantity):
            return cls(v.magnitude, v.units)
        if isinstance(v, str):
            q = ureg(v)
            return cls(q.magnitude, q.units)
        if isinstance(v, (int, float)):
            raise ValueError("Numeric values require a unit")
        raise ValueError(f"Unsupported type: {type(v)}")

    @staticmethod
    def from_any(v, default_unit=None):
        """
        Parse from:
        - pint.Quantity
        - string ("5 ml")
        - bare number + default_unit
        """
        if isinstance(v, ChemUnitQuantity):
            return v

        if isinstance(v, Quantity):
            return ChemUnitQuantity(v.magnitude, v.units)

        if isinstance(v, str):
            q = ureg(v)
            return ChemUnitQuantity(q.magnitude, q.units)

        if isinstance(v, (int, float)):
            if default_unit is None:
                raise ValueError("Numeric input requires a unit.")
            return ChemUnitQuantity(v, default_unit)

        raise TypeError(f"Cannot convert {v!r} to ChemUnitQuantity.")

    def __new__(cls, value, unit=None) -> "ChemUnitQuantity":
        # Case 1: string "5 ml"
        if isinstance(value, str) and unit is None:
            q = ureg(value)
            return super().__new__(cls, q.magnitude, q.units)  # type: ignore[return-value]

        # Case 2: magnitude + unit
        if unit is not None:
            return super().__new__(cls, value, unit)  # type: ignore[return-value]

        # Case 3: use pint.Quantity as input
        if isinstance(value, Quantity):
            return super().__new__(cls, value.magnitude, value.units)  # type: ignore[return-value]

        raise TypeError(f"Invalid input for ChemUnitQuantity: {value!r}, unit={unit!r}")

    # ----------- ADDITION (a + b) -----------

    def __add__(self, other):
        other_q = self.from_any(other, default_unit=self.units)
        result = super().__add__(other_q)
        return ChemUnitQuantity(result.magnitude, result.units)

    def __radd__(self, other):  # type: ignore[override]
        return self.__add__(other)

    # ----------- SUBTRACTION (a - b) -----------

    def __sub__(self, other):
        other_q = self.from_any(other, default_unit=self.units)
        result = super().__sub__(other_q)
        return ChemUnitQuantity(result.magnitude, result.units)

    def __rsub__(self, other):
        other_q = self.from_any(other, default_unit=self.units)
        result = other_q.__sub__(self)  # the order flips here
        return ChemUnitQuantity(result.magnitude, result.units)

    # ----------- MULTIPLICATION (a * b) -----------

    def __mul__(self, other):
        if isinstance(other, (int, float)):
            result = super().__mul__(other)
            return ChemUnitQuantity(result.magnitude, result.units)

        # Allow multiplication with another quantity
        other_q = self.from_any(other)
        result = super().__mul__(other_q)
        return ChemUnitQuantity(result.magnitude, result.units)

    def __rmul__(self, other):  # type: ignore[override]
        return self.__mul__(other)

    # ----------- DIVISION (a / b) -----------

    def __truediv__(self, other):
        if isinstance(other, (int, float)):
            result = super().__truediv__(other)
            return ChemUnitQuantity(result.magnitude, result.units)

        other_q = self.from_any(other)
        result = super().__truediv__(other_q)
        return ChemUnitQuantity(result.magnitude, result.units)

    def __rtruediv__(self, other):
        other_q = self.from_any(other)
        result = other_q.__truediv__(self)
        return ChemUnitQuantity(result.magnitude, result.units)

    # ----------- PRETTY PRINT -----------

    def __repr__(self):
        return f"<ChemUnitQuantity({self.magnitude}, '{self.units}')>"


class ChemQuantityValidator(PydanticPintQuantity):

    def __init__(self, _arg, **kwargs):
        kwargs.update(strict=False, ser_mode="str", ureg=ureg)
        super().__init__(_arg, **kwargs)

    def validate(self, *args, **kwargs) -> ChemUnitQuantity:
        v = super().validate(*args, **kwargs)
        return ChemUnitQuantity(v)

    def serialize(self, *args, **kwargs) -> dict | str | ChemUnitQuantity:
        v = super().serialize(*args, **kwargs)
        if isinstance(v, Quantity):
            return ChemUnitQuantity(v)
        return v


if __name__ == "__main__":
    a = ChemUnitQuantity(1, "ml")
    b = ChemUnitQuantity(1, "ml")
    print(a + b)  # 2 milliliter

    c = ChemUnitQuantity(5, "ml")
    print(c + 2)  # 7 milliliter

    d = ChemUnitQuantity.parse("3 ml")
    print(d + 4)  # 7 milliliter
