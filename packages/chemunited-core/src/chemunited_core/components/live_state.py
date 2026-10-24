"""Device pictures for the live platform view, from the commands a device gets.

Qt-free, so the desktop canvas and the work-server share it and draw the same:

- ``iter_apply_kwargs`` turns a command's parameters into the keyword
  arguments ``ComponentData.apply()`` takes;
- ``rotor_links`` lists the channels a rotary valve's rotor draws;
- ``picture_kind`` and ``visual_state`` say which picture a component has
  and what it looks like now;
- ``LivePicture`` follows one device's picture through the commands it gets,
  assuming nothing from the design state.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from functools import cache
from typing import TYPE_CHECKING, Any

from chemunited_core.components.valve import ValveComponentData, connection_from_rotor

if TYPE_CHECKING:
    from chemunited_core.components.component import ComponentData

RotorLink = tuple[int, int]

# The commands that set each picture. Any other PUT/POST leaves the picture
# unknown: the live view can't tell what it did to the device.
PICTURE_COMMANDS: dict[str, frozenset[str]] = {
    "rotor": frozenset({"position"}),
    "solenoid": frozenset({"open", "close", "power-on", "power-off"}),
    "two-way": frozenset({"open", "close", "power-on", "power-off"}),
    "mfc": frozenset({"set-flow-rate", "stop"}),
    "relay": frozenset({"power-on", "power-off", "multiple_channel"}),
}


class UnrecognisedCommand(ValueError):
    """A command doesn't say what its device looks like afterwards."""


def normalize_connect_pairs(parsed: object) -> list[tuple[int, int]] | None:
    """The port pairs in a parsed ``connect`` value, or None for any other shape."""
    if not isinstance(parsed, list) or not parsed:
        return None
    # Flat pair: [a, b] - both elements are numbers, not nested lists.
    if len(parsed) == 2 and all(isinstance(x, (int, float)) for x in parsed):
        return [tuple(parsed)]  # type: ignore[list-item]
    # One or more pairs: [[a, b], ...] - every element is itself a 2-element list.
    if all(isinstance(item, list) and len(item) == 2 for item in parsed):
        return [tuple(item) for item in parsed]
    return None


def iter_apply_kwargs(
    command: str, params: Mapping[str, Any]
) -> Iterator[dict[str, Any]]:
    """The keyword arguments for each ``apply()`` call one command makes.

    ``PositionParameter.connect`` (chemunited_core.protocols.valves) is
    deliberately str-typed for a GUI dropdown, and its JSON shape isn't
    consistent - a flat pair "[a, b]" or a wrapped list of pairs
    "[[a, b]]"/"[[a, b], [c, d]]". ``apply()`` takes a single flat pair, so
    detect the shape, unwrap, and yield one set of kwargs per pair. Any other
    command's params pass through unchanged.
    """
    if command == "position" and isinstance(params.get("connect"), str):
        try:
            parsed = json.loads(params["connect"])
        except (ValueError, TypeError):
            parsed = None
        pairs = normalize_connect_pairs(parsed)
        if pairs:
            for pair in pairs:
                yield {**params, "connect": pair}
            return
    yield dict(params)


def rotor_links(data: ValveComponentData) -> list[RotorLink]:
    """The channels a rotary valve's rotor draws, as pairs of rotor slots.

    Slot 1 is the top one, counting clockwise; 0 is the hub. A slot can have
    no stator port behind it. ``RotorChannel.paint`` in the desktop app draws
    exactly these, and the dashboard draws them on the exported slot points.
    """
    slots = list(data.rotor_ports[0])
    unpaired = list(slots)
    links: list[RotorLink] = []
    if 0 in data.ports_by_number:
        hub = data.rotor_ports[1][0]
        for i, value in enumerate(slots):
            if value == hub:
                unpaired[i] = None
                links.append((0, i + 1))
    for i, value in enumerate(slots):
        if not value:
            continue
        for j, other in enumerate(unpaired):
            if other == value and j != i:
                link = (min(i, j) + 1, max(i, j) + 1)
                if link not in links:
                    links.append(link)
                break
    return links


@cache
def _picture_classes() -> tuple[tuple[type, str], ...]:
    # Imported here: figure_registry imports this module.
    from chemunited_core.figure_registry.controllers import MFCComponentData
    from chemunited_core.figure_registry.rotary_valve import RotaryValveData
    from chemunited_core.figure_registry.solenoid_valve import (
        SolenoidValve2WayData,
        SolenoidValveData,
    )
    from chemunited_core.figure_registry.technical import MultiChannelRelayData

    return (
        (RotaryValveData, "rotor"),
        (SolenoidValveData, "solenoid"),
        (SolenoidValve2WayData, "two-way"),
        (MFCComponentData, "mfc"),
        (MultiChannelRelayData, "relay"),
    )


def picture_kind_of(data_class: type) -> str | None:
    """The picture drawn for components of *data_class*, if any."""
    for cls, kind in _picture_classes():
        if issubclass(data_class, cls):
            return kind
    return None


def picture_kind(data: ComponentData) -> str | None:
    """``"rotor"``, ``"solenoid"``, ``"two-way"``, ``"mfc"``, ``"relay"``, or None."""
    return picture_kind_of(type(data))


def visual_state(data: ComponentData) -> dict[str, Any]:
    """What *data*'s picture looks like now; ``{}`` if it has none."""
    kind = picture_kind(data)
    if kind == "rotor":
        return {"links": [list(link) for link in rotor_links(data)]}  # type: ignore[arg-type]
    if kind == "solenoid":
        return {"open": bool(data.opened)}  # type: ignore[attr-defined]
    if kind == "two-way":
        return {"position": 1 if data.opened else 2}  # type: ignore[attr-defined]
    if kind == "mfc":
        return {"active": data.flowrate_si > 0.0}  # type: ignore[attr-defined]
    if kind == "relay":
        return {"channels": [bool(value) for value in data.active]}  # type: ignore[attr-defined]
    return {}


def _connected(data: ValveComponentData, pair: object) -> bool:
    _, active = connection_from_rotor(
        stator_ports=data.stator_ports, rotor_ports=data.rotor_ports
    )
    a, b = (int(port) for port in pair)  # type: ignore[attr-defined]
    return (a, b) in active or (b, a) in active


class LivePicture:
    """One device's picture, followed through the commands it gets.

    Nothing comes from the design state: a part no command has set yet is
    None (for a relay, each channel nothing has switched yet).
    """

    def __init__(self, data: ComponentData) -> None:
        self.data = data
        self.kind = picture_kind(data)
        self._known_channels: set[int] = set()

    def apply(
        self, command: str, params: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        """Apply *command* and return the picture after it.

        Raises ``UnrecognisedCommand`` if *command* doesn't say what the
        device looks like afterwards: a command the picture doesn't know,
        missing or invalid parameters, or a valve position the valve can't
        take.
        """
        params = dict(params or {})
        name = self.data.name
        if self.kind is None or command not in PICTURE_COMMANDS[self.kind]:
            raise UnrecognisedCommand(
                f"'{command}' doesn't say what {name} looks like afterwards."
            )
        channel = None
        if self.kind == "relay" and command != "multiple_channel":
            channel = self._channel(params)
        try:
            calls = list(iter_apply_kwargs(command, params))
            for kwargs in calls:
                self.data.apply(command, **kwargs)
            if self.kind == "rotor":
                for kwargs in calls:
                    if not _connected(self.data, kwargs["connect"]):  # type: ignore[arg-type]
                        raise UnrecognisedCommand(
                            f"{name} can't connect ports {kwargs['connect']}."
                        )
        except UnrecognisedCommand:
            raise
        except Exception as exc:
            raise UnrecognisedCommand(
                f"Could not apply '{command}' {params} to {name}: {exc}"
            ) from exc

        picture = visual_state(self.data)
        if self.kind == "relay":
            if channel is None:
                self._known_channels = set(range(len(picture["channels"])))
            else:
                self._known_channels.add(channel)
            picture["channels"] = [
                value if i in self._known_channels else None
                for i, value in enumerate(picture["channels"])
            ]
        return picture

    def _channel(self, params: Mapping[str, Any]) -> int:
        count = len(self.data.active)  # type: ignore[attr-defined]
        try:
            index = int(params["channel"]) - 1
        except (KeyError, TypeError, ValueError):
            index = -1
        if not 0 <= index < count:
            raise UnrecognisedCommand(
                f"{self.data.name} has no channel {params.get('channel')!r} "
                f"(it has 1 to {count})."
            )
        return index
