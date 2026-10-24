"""LcdDisplay — an LCD readout on the platform drawing, bound to a device variable."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from chemunited_core.protocols import get_protocol_class
from chemunited_quantities import ChemUnitQuantity


class LcdDisplay(BaseModel):
    """What ``platform.add_display(...)`` in ``draw/setup.py`` records.

    On the dashboard's live view the LCD shows the latest monitoring reading
    of ``component``'s ``command`` (with ``kwargs``). LCDs never read a device
    themselves, and aren't devices: no connectivity, no simulation.
    """

    name: str
    position: tuple[float, float] = (0.0, 0.0)
    component: str
    command: str
    kwargs: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name", "component", "command")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value


def _json_value(value: Any) -> Any:
    if isinstance(value, ChemUnitQuantity):
        return str(value)
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def device_variables(figure: str, name: str) -> dict[str, dict[str, Any]]:
    """The variables an LCD can show for a device: its protocol's GET commands.

    Maps each command to its parameters' defaults, read from the device's
    protocol definition in chemunited-core, so no device has to be connected.
    """
    protocol = get_protocol_class(figure)(name).sync()
    return {
        signature.command: {
            key: _json_value(value) for key, value in signature.parameters.items()
        }
        for signature in protocol.get_commands.values()
    }
