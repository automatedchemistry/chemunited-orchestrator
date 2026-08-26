"""Example custom routes for this project.

See docs/api-reference.md#custom-routes. Register a function name here to
call it via POST /custom/<name> (body = keyword arguments) — the frontend
or an LLM can call it directly by name, without a code change to
chemunited_workflow itself.
"""

from __future__ import annotations

from chemunited_workflow import CustomRouteContext


def residence_time_min(flow_rate_ml_min: float, reactor_volume_ml: float) -> float:
    """Residence time (minutes) = reactor volume / flow rate.

    A pure computation over the call's own kwargs — no device involved.
    """
    return reactor_volume_ml / flow_rate_ml_min


def chiller_temperature_f() -> float:
    """Fahrenheit reading from the real `chiller` component, reached through
    CustomRouteContext.platform — a throwaway Platform opened just for this
    call and closed once it returns.
    """
    platform = CustomRouteContext.platform
    if platform is None:
        raise RuntimeError(
            "No custom route call in flight: CustomRouteContext.platform is unset."
        )
    celsius = platform["chiller"].get("temperature")
    return celsius * 9 / 5 + 32


def set_chiller_setpoint(celsius: float) -> dict:
    """Drive the real `chiller` component — an action with a side effect,
    not just a reading. Demonstrates that a custom route can command
    equipment, not only report values.
    """
    platform = CustomRouteContext.platform
    if platform is None:
        raise RuntimeError(
            "No custom route call in flight: CustomRouteContext.platform is unset."
        )
    platform["chiller"].put("temperature", value=celsius)
    return {"setpoint_celsius": celsius}


CUSTOM_ROUTES = {
    "residence_time_min": residence_time_min,
    "chiller_temperature_f": chiller_temperature_f,
    "set_chiller_setpoint": set_chiller_setpoint,
}
