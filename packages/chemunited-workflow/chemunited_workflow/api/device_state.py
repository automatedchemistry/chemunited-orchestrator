"""Live state of each device, kept in memory for the dashboard's platform view.

Fed by the command events the device clients report (see ``command_events``):
``started`` marks the device running and records the command, ``finished``
marks it done, and ``failed`` marks it failed with its picture unknown — a
command that failed or timed out may or may not have run. A command from the
device panel is done as soon as the device accepts it: the panel doesn't wait
for the device to finish. With a picture
deriver installed (``command_tracker``, which needs chemunited-core), each
command also redraws the device's picture. Every record starts unknown when
the project loads; nothing is assumed from the design state.

The LCD displays drawn in the desktop app show monitoring readings: the store
gets each one through ``record_reading`` and keeps it, as text, for every LCD
bound to that variable, followed by the LCD's unit when the reading is a
number. LCDs never read a device themselves.

Every change gets the next ``seq``. A bounded log of the changes lets a stream
that reconnects replay what it missed (see ``routers/platform.py``).
"""

from __future__ import annotations

import copy
import json
import secrets
import threading
from collections import deque
from collections.abc import Callable, Collection, Iterable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol

from loguru import logger

from ..command_events import CommandEvent

DeviceStatus = Literal["unknown", "running", "done", "failed"]

CHANGE_LOG_SIZE = 500


class UnknownPicture(Exception):
    """A command doesn't say what its device looks like afterwards."""


class PictureDeriver(Protocol):
    """Turns commands into device pictures (see ``command_tracker``)."""

    def kind(self, component: str) -> str | None:
        """The picture drawn for *component* (``"rotor"``, ``"solenoid"``, …), if any."""
        ...

    def derive(
        self, component: str, command: str, params: Mapping[str, Any] | None
    ) -> dict[str, Any]:
        """The picture after *command*; raises ``UnknownPicture`` if it can't tell."""
        ...


@dataclass
class DeviceCommand:
    name: str
    params: dict[str, Any] | None
    at: str
    run: str | None
    node: str | None


@dataclass
class DeviceState:
    component: str
    kind: str | None = None
    status: DeviceStatus = "unknown"
    command: DeviceCommand | None = None
    picture: dict[str, Any] | None = None
    error: str | None = None
    # The command whose finished/failed event still moves the status: a newer
    # command to the same device (say, Stop from the device panel while a run
    # waits on the pump) takes over from an older one still waiting.
    call_id: int = field(default=0, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "status": self.status,
            "command": None if self.command is None else asdict(self.command),
            "picture": copy.deepcopy(self.picture),
            "error": self.error,
        }


def _display_text(value: Any) -> str | None:
    """An LCD shows text: a reading's value as a string."""
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


def _with_unit(text: str | None, unit: str) -> str | None:
    """*text* followed by *unit* when it's a number: ``"1.02"`` → ``"1.02 bar"``.

    Anything else is left as it is, so a device that reports its own unit
    ("24.3 degC") never shows two.
    """
    if text is None or not unit:
        return text
    try:
        float(text)
    except ValueError:
        return text
    return f"{text} {unit}"


class DeviceStateStore:
    """The live state of every device and LCD in the loaded project. Thread-safe.

    ``displays`` maps each LCD's name to the monitoring key of the variable it
    shows, and ``display_units`` to its unit, if it has one; ``monitored_keys``
    returns the keys in the monitoring list, so an LCD can say it isn't
    monitored.
    """

    def __init__(
        self,
        components: Iterable[str] = (),
        *,
        deriver: PictureDeriver | None = None,
        displays: Mapping[str, str] | None = None,
        display_units: Mapping[str, str] | None = None,
        monitored_keys: Callable[[], Collection[str]] | None = None,
        log_size: int = CHANGE_LOG_SIZE,
    ) -> None:
        # Identifies this store in stream event ids, so a browser that
        # reconnects after a project reload or a server restart gets a fresh
        # snapshot instead of a replay of another store's changes.
        self.epoch = secrets.token_hex(4)
        self._lock = threading.Lock()
        self._deriver = deriver
        self._devices: dict[str, DeviceState] = {}
        for name in components:
            self._devices[name] = self._new_state(name)
        self._display_keys = dict(displays or {})
        self._display_units = dict(display_units or {})
        self._monitored_keys = monitored_keys
        self._displays: dict[str, dict[str, Any]] = {
            name: {"value": None, "at": None, "error": None}
            for name in self._display_keys
        }
        self._seq = 0
        self._log: deque[tuple[int, dict[str, Any]]] = deque(maxlen=log_size)

    @property
    def has_pictures(self) -> bool:
        return self._deriver is not None

    @property
    def seq(self) -> int:
        with self._lock:
            return self._seq

    def observer(self, run_id: str | None = None) -> StateObserver:
        """A ``command_observer`` for the device clients of one run (or none)."""
        return StateObserver(self, run_id)

    def apply(self, event: CommandEvent, run_id: str | None = None) -> None:
        with self._lock:
            state = self._devices.get(event.component)
            if state is None:
                state = self._devices[event.component] = self._new_state(
                    event.component
                )
            if event.kind == "started":
                self._start(state, event, run_id)
            elif event.call_id != state.call_id:
                return
            elif event.kind == "finished":
                state.status = "unknown" if state.error else "done"
            else:
                state.status = "failed"
                state.picture = None
                state.error = event.error or "The command failed."
            self._record_change({"devices": {state.component: state.to_dict()}})

    def record_reading(self, key: str, reading: Mapping[str, Any]) -> None:
        """A monitoring reading: shows it on every LCD bound to *key*."""
        names = [name for name, bound in self._display_keys.items() if bound == key]
        if not names:
            return
        error = reading.get("error")
        text = None if error else _display_text(reading.get("value"))
        with self._lock:
            for name in names:
                display = {
                    "value": _with_unit(text, self._display_units.get(name, "")),
                    "at": reading.get("time"),
                    "error": None if error is None else str(error),
                    "monitored": True,
                }
                self._displays[name] = display
                self._record_change({"displays": {name: dict(display)}})

    def snapshot(self) -> dict[str, Any]:
        monitored = set(self._monitored_keys()) if self._monitored_keys else set()
        with self._lock:
            return {
                "seq": self._seq,
                "pictures": self.has_pictures,
                "devices": {
                    name: state.to_dict() for name, state in self._devices.items()
                },
                "displays": {
                    name: {
                        **display,
                        "monitored": self._display_keys[name] in monitored,
                    }
                    for name, display in self._displays.items()
                },
            }

    def changes_since(self, seq: int) -> list[dict[str, Any]] | None:
        """The changes after *seq*, oldest first.

        None if the log no longer reaches back that far, or *seq* is from
        later than this store has got to: the caller then needs a snapshot.
        """
        with self._lock:
            if seq > self._seq:
                return None
            if seq == self._seq:
                return []
            if not self._log or self._log[0][0] > seq + 1:
                return None
            return [{"seq": s, **change} for s, change in self._log if s > seq]

    # ── internals (called with the lock held) ────────────────────────────────

    def _new_state(self, component: str) -> DeviceState:
        kind = None
        if self._deriver is not None:
            try:
                kind = self._deriver.kind(component)
            except Exception:
                logger.opt(exception=True).warning(
                    "Live view: no picture kind for '{}'", component
                )
        return DeviceState(component=component, kind=kind)

    def _start(
        self, state: DeviceState, event: CommandEvent, run_id: str | None
    ) -> None:
        command = DeviceCommand(
            name=event.command.strip("/"),
            params=dict(event.params) if event.params else None,
            at=datetime.now().isoformat(),
            run=run_id,
            node=event.node,
        )
        state.call_id = event.call_id
        state.status = "running"
        state.command = command
        state.error = None
        if state.kind is None or self._deriver is None:
            return
        try:
            state.picture = self._deriver.derive(
                state.component, command.name, command.params
            )
        except UnknownPicture as exc:
            state.picture = None
            state.error = str(exc)
        except Exception as exc:
            logger.opt(exception=True).warning(
                "Live view: could not work out the picture of '{}' after '{}'",
                state.component,
                command.name,
            )
            state.picture = None
            state.error = f"Could not work out the picture: {exc}"

    def _record_change(self, change: dict[str, Any]) -> None:
        self._seq += 1
        self._log.append((self._seq, change))


class StateObserver:
    """The ``command_observer`` the device clients call; it updates the store."""

    def __init__(self, store: DeviceStateStore, run_id: str | None = None) -> None:
        self._store = store
        self._run_id = run_id

    def __call__(self, event: CommandEvent) -> None:
        self._store.apply(event, self._run_id)
