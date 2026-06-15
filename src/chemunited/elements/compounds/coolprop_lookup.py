from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from math import isfinite

from chemunited_core.utils import ChemUnitQuantity

STANDARD_TEMPERATURE_K = 298.15
STANDARD_PRESSURE_PA = 101325.0

PropsSIFunc = Callable[[str, str, float, str, float, str], float]


@dataclass(frozen=True)
class CoolPropLookupResult:
    fluid_name: str
    values: dict[str, ChemUnitQuantity]
    errors: dict[str, str]


def is_coolprop_available() -> bool:
    try:
        _load_props_si()
    except ImportError:
        return False
    return True


def lookup_compound_properties(
    compound_name: str,
    *,
    props_si: PropsSIFunc | None = None,
    temperature_k: float = STANDARD_TEMPERATURE_K,
    pressure_pa: float = STANDARD_PRESSURE_PA,
) -> CoolPropLookupResult:
    """Look up ChemUnited compound fields with CoolProp-style units."""
    name = compound_name.strip()
    if not name:
        raise ValueError("Enter a compound name before using CoolProp.")

    props = props_si or _load_props_si()
    candidates = _candidate_names(name)
    last_result: CoolPropLookupResult | None = None

    for candidate in candidates:
        result = _lookup_candidate(
            props,
            candidate,
            temperature_k=temperature_k,
            pressure_pa=pressure_pa,
        )
        if result.values:
            return result
        last_result = result

    if last_result is not None:
        return last_result
    return CoolPropLookupResult(name, {}, {"name": "No CoolProp fluid name tried."})


def _load_props_si() -> PropsSIFunc:
    from CoolProp.CoolProp import PropsSI

    return PropsSI


def _candidate_names(name: str) -> list[str]:
    title_name = name.title()
    if title_name == name:
        return [name]
    return [name, title_name]


def _lookup_candidate(
    props_si: PropsSIFunc,
    fluid_name: str,
    *,
    temperature_k: float,
    pressure_pa: float,
) -> CoolPropLookupResult:
    values: dict[str, ChemUnitQuantity] = {}
    errors: dict[str, str] = {}

    molar_mass = _try_props(
        props_si,
        "MOLARMASS",
        "",
        0,
        "",
        0,
        fluid_name,
    )
    if molar_mass is None:
        errors["molecular_weight"] = "CoolProp did not return molar mass."
    else:
        values["molecular_weight"] = ChemUnitQuantity(molar_mass, "kg/mol").to("g/mol")

    cp_gas = _try_props(
        props_si,
        "CPMOLAR",
        "T|gas",
        temperature_k,
        "P",
        pressure_pa,
        fluid_name,
    )
    if cp_gas is None:
        cp_gas = _try_props(
            props_si,
            "CP0MOLAR",
            "T",
            temperature_k,
            "P",
            pressure_pa,
            fluid_name,
        )
    if cp_gas is None:
        errors["cp_gas"] = "CoolProp did not return gas heat capacity."
    else:
        values["cp_gas"] = ChemUnitQuantity(cp_gas, "J/(mol*K)")

    cp_liquid = _try_props(
        props_si,
        "CPMOLAR",
        "T|liquid",
        temperature_k,
        "P",
        pressure_pa,
        fluid_name,
    )
    if cp_liquid is None:
        errors["cp_liquid"] = "CoolProp did not return liquid heat capacity."
    else:
        values["cp_liquid"] = ChemUnitQuantity(cp_liquid, "J/(mol*K)")

    density_liquid = _try_props(
        props_si,
        "D",
        "T|liquid",
        temperature_k,
        "P",
        pressure_pa,
        fluid_name,
    )
    if density_liquid is None:
        errors["density_liquid"] = "CoolProp did not return liquid density."
    else:
        values["density_liquid"] = ChemUnitQuantity(density_liquid, "kg/m^3")

    return CoolPropLookupResult(fluid_name, values, errors)


def _try_props(
    props_si: PropsSIFunc,
    output: str,
    input_1: str,
    value_1: float,
    input_2: str,
    value_2: float,
    fluid_name: str,
) -> float | None:
    try:
        value = float(props_si(output, input_1, value_1, input_2, value_2, fluid_name))
    except Exception:
        return None
    if not isfinite(value):
        return None
    return value
