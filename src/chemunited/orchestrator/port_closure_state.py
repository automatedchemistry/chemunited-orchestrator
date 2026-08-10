from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from chemunited_core.common.enums import ConnectionType
from chemunited_core.components.enums import PortClosure


def build_port_closure_payload(components: Iterable[Any]) -> dict[str, dict[str, bool]]:
    """Hydraulic ports only; only CAPPED entries (absence == OPEN, the default)."""
    payload: dict[str, dict[str, bool]] = {}
    for component in components:
        component_data = getattr(component, "inf", component)
        capped = {
            str(num): True
            for num, port in getattr(component_data, "ports_by_number", {}).items()
            if port.category == ConnectionType.HYDRAULIC
            and port.closure == PortClosure.CAPPED
        }
        if capped:
            name = str(getattr(component_data, "name", ""))
            if name:
                payload[name] = capped
    return payload


def apply_port_closure_payload(components: Mapping[str, Any], payload: object) -> None:
    if not isinstance(payload, dict):
        return
    for component_name, port_payload in payload.items():
        component = components.get(str(component_name))
        if component is None or not isinstance(port_payload, dict):
            continue
        set_port_closed = getattr(
            getattr(component, "graph", None), "set_port_closed", None
        )
        if not callable(set_port_closed):
            continue
        for port_num_str, closed in port_payload.items():
            try:
                port_num = int(port_num_str)
            except (TypeError, ValueError):
                continue
            set_port_closed(port_num, bool(closed))
