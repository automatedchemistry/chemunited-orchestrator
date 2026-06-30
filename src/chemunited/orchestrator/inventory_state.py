from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from chemunited_core.common.enums import PhaseKind
from chemunited_core.compounds import COMPOUNDS


def coerce_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def ensure_air_defaults_for_components(components: Iterable[Any]) -> None:
    for component in components:
        component_data = getattr(component, "inf", component)
        ensure_air_defaults(component_data)


def ensure_air_defaults(component_data: Any) -> None:
    apply_air_defaults = getattr(component_data, "apply_air_defaults", None)
    if callable(apply_air_defaults):
        apply_air_defaults()

    for inventory in getattr(component_data, "internal_inventories", {}).values():
        if inventory.gas_content.initial_species:
            continue

        gas_content = inventory.gas_content
        gas_volume = float(getattr(gas_content, "volume", 0.0) or 0.0)
        if gas_volume <= 0.0:
            capacity = float(getattr(component_data, "capacity_value", 0.0) or 0.0)
            if capacity <= 0.0:
                continue
            liq_volume = float(getattr(inventory.liq_content, "volume", 0.0) or 0.0)
            remaining = capacity - liq_volume
            if remaining <= 0.0:
                continue
            gas_volume = remaining
            gas_content.volume = remaining

        air = COMPOUNDS["air"]
        gas_content.phase_kind = PhaseKind.GAS
        gas_content.initial_species = {
            "air": gas_volume
            / air.molar_volume_gas(
                gas_content.initial_temperature,
                gas_content.initial_pressure,
            )
        }


def build_inventory_status_payload(components: Iterable[Any]) -> dict[str, dict]:
    payload: dict[str, dict] = {}
    for component in components:
        component_data = getattr(component, "inf", component)
        ensure_air_defaults(component_data)
        component_payload = _component_inventory_payload(component_data)
        if component_payload:
            component_name = str(getattr(component_data, "name", ""))
            if component_name:
                payload[component_name] = component_payload
    return payload


def apply_inventory_status_payload(
    components: Mapping[str, Any],
    payload: object,
) -> bool:
    if not isinstance(payload, dict):
        ensure_air_defaults_for_components(components.values())
        return False

    restored = False
    for component_name, inventory_payload in payload.items():
        component = components.get(str(component_name))
        if component is None:
            continue
        component_data = getattr(component, "inf", component)
        if _apply_component_inventory_payload(component_data, inventory_payload):
            restored = True

    ensure_air_defaults_for_components(components.values())
    return restored


def _component_inventory_payload(component_data: Any) -> dict[str, dict]:
    payload: dict[str, dict[str, dict[str, object]]] = {}
    for inventory_key, inventory in getattr(
        component_data, "internal_inventories", {}
    ).items():
        phases: dict[str, dict[str, object]] = {}
        for phase_name, content in (
            (PhaseKind.LIQUID.value, inventory.liq_content),
            (PhaseKind.GAS.value, inventory.gas_content),
        ):
            species = {
                str(name): float(amount)
                for name, amount in content.initial_species.items()
                if float(amount) > 0.0
            }
            phases[phase_name] = {
                "volume": float(content.volume),
                "initial_species": species,
            }
        if phases:
            payload[str(inventory_key)] = phases
    return payload


def _apply_component_inventory_payload(component_data: Any, payload: object) -> bool:
    if not isinstance(payload, dict):
        return False

    restored = False
    inventories = getattr(component_data, "internal_inventories", {})
    for inventory_key, phase_payloads in payload.items():
        inventory = inventories.get(str(inventory_key))
        if inventory is None or not isinstance(phase_payloads, dict):
            continue

        for phase in (PhaseKind.LIQUID, PhaseKind.GAS):
            phase_payload = phase_payloads.get(phase.value)
            if not isinstance(phase_payload, dict):
                continue

            content = (
                inventory.liq_content
                if phase == PhaseKind.LIQUID
                else inventory.gas_content
            )
            content.phase_kind = phase
            content.volume = coerce_float(phase_payload.get("volume"), content.volume)
            species_payload = phase_payload.get("initial_species", {})
            if not isinstance(species_payload, dict):
                continue
            content.initial_species = {
                str(name): amount
                for name, raw_amount in species_payload.items()
                if (amount := coerce_float(raw_amount)) > 0.0
            }
            restored = True
    return restored
