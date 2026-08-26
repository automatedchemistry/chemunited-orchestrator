"""SimClient and SimCommand — workflow-side interface for mode 1 simulation."""

from __future__ import annotations

import heapq
import json
import queue
import threading
import time
from dataclasses import dataclass, field
from itertools import count
from pathlib import Path
from typing import Any, Iterator, cast

from chemunited_core.components import ComponentData
from chemunited_workflow import Platform, RunCancelledError
from chemunited_workflow.clients import ComponentClient

from .clock import SimClock


@dataclass
class SimCommand:
    component: str
    command: str
    kwargs: dict = field(default_factory=dict)
    pre_applied: bool = False


def _wait_until_sim_time(
    clock: SimClock,
    deadline: float,
    stop_event: threading.Event,
) -> None:
    """Wait until the simulated deadline, aborting on simulation stop."""
    while clock.now() < deadline:
        if stop_event.is_set():
            raise RunCancelledError("Run was cancelled.")
        time.sleep(0.0001)
    if stop_event.is_set():
        raise RunCancelledError("Run was cancelled.")


def _normalize_connect_pairs(parsed: object) -> list[tuple[int, int]] | None:
    if not isinstance(parsed, list) or not parsed:
        return None
    # Flat pair: [a, b] - both elements are numbers, not nested lists.
    if len(parsed) == 2 and all(isinstance(x, (int, float)) for x in parsed):
        return [tuple(parsed)]  # type: ignore[list-item]
    # One or more pairs: [[a, b], ...] - every element is itself a 2-element list.
    if all(isinstance(item, list) and len(item) == 2 for item in parsed):
        return [tuple(item) for item in parsed]
    return None


def iter_apply_kwargs(command: str, kwargs: dict) -> Iterator[dict]:
    """Normalize a "position" command's ``connect`` kwarg before calling apply().

    ``PositionParameter.connect`` (chemunited_core.protocols.valves) is
    deliberately str-typed for a GUI dropdown, and its JSON shape isn't
    consistent - a flat pair "[a, b]" or a wrapped list of pairs
    "[[a, b]]"/"[[a, b], [c, d]]". ``ComponentData.apply()`` expects a single
    flat pair, so detect the shape, unwrap, and iterate - one ``apply()`` call
    per pair. Mirrors chemunited-orchestrator's pool_commands.py, which does
    the same unwrapping for its live GUI-replay path; this is the equivalent
    for the actual physics application here.
    """
    if command == "position" and isinstance(kwargs.get("connect"), str):
        try:
            parsed = json.loads(kwargs["connect"])
        except (json.JSONDecodeError, ValueError, TypeError):
            parsed = None
        pairs = _normalize_connect_pairs(parsed)
        if pairs:
            for pair in pairs:
                yield {**kwargs, "connect": pair}
            return
    yield kwargs


def write_pool_log(
    project_path: Path,
    component: str,
    *,
    method: str,
    command: str,
    params: dict | None,
) -> None:
    """Append one command entry to project_path/log/pool/<component>.jsonl.

    Mirrors chemunited-workflow's ComponentClient._write_json_log format so the
    same viewer tooling can render simulated runs.
    """
    path = project_path / "log" / "pool" / f"{component}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "component": component,
        "method": method,
        "command": command,
        "params": params,
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(data) + "\n")


class SimClient:
    """Duck-types chemunited_workflow.clients.ComponentClient for mode 1 (workflow)
    simulation, without inheriting from it - it stands in for a real HTTP
    device client, not one, so Platform's type-checking is silenced at the
    call site instead (see server.py).

    put() calls apply() immediately (setting component state on the workflow
    thread), enqueues a pre-applied SimCommand so the worker resyncs the graph,
    and waits on SimClock for scheduled follow-ups (e.g. auto-stop after a
    volume dispense). This mirrors a real synchronous device client: the call
    returns only after the simulated component has finished its finite work.
    get() delegates directly to ComponentData.get().
    """

    def __init__(
        self,
        name: str,
        component: ComponentData,
        clock: SimClock,
        cmd_queue: queue.Queue,
        project_path: Path,
        stop_event: threading.Event | None = None,
    ) -> None:
        self._name = name
        self._component = component
        self._clock = clock
        self._queue = cmd_queue
        self._project_path = project_path
        self._stop_event = stop_event or threading.Event()

    def put(
        self,
        command: str,
        *,
        wait_time: float = 0.0,
        wait_feedback_status: bool = False,
        feedback_status_command: str = "",
        feedback_answer: str = "true",
        **kwargs: Any,
    ) -> None:
        """Apply a command and wait for its inferred simulated completion.

        The named execution options are accepted only for compatibility with
        archived process files. They are deliberately excluded from physics
        kwargs; wait_time acts as a minimum simulated delay, while device
        feedback completion is represented by PutResult.scheduled.
        """
        del wait_feedback_status, feedback_status_command, feedback_answer
        self._raise_if_cancelled()
        write_pool_log(
            self._project_path,
            self._name,
            method="PUT",
            command=command,
            params=kwargs or None,
        )
        started_at = self._clock.now()
        pending: list[tuple[float, int, Any]] = []
        order = count()
        for call_kwargs in iter_apply_kwargs(command, kwargs):
            result = self._component.apply(command, **call_kwargs)
            for scheduled in result.scheduled:
                heapq.heappush(
                    pending,
                    (started_at + scheduled.dt, next(order), scheduled),
                )
        self._queue.put(
            SimCommand(
                component=self._name, command=command, kwargs=kwargs, pre_applied=True
            )
        )
        while pending:
            deadline, _, scheduled = heapq.heappop(pending)
            _wait_until_sim_time(self._clock, deadline, self._stop_event)
            result = self._component.apply(scheduled.command, **scheduled.kwargs)
            self._queue.put(
                SimCommand(
                    component=self._name,
                    command=scheduled.command,
                    kwargs=scheduled.kwargs,
                    pre_applied=True,
                )
            )
            scheduled_at = self._clock.now()
            for follow_up in result.scheduled:
                heapq.heappush(
                    pending,
                    (scheduled_at + follow_up.dt, next(order), follow_up),
                )

        minimum_deadline = started_at + max(0.0, float(wait_time))
        _wait_until_sim_time(self._clock, minimum_deadline, self._stop_event)

    def get(
        self,
        command: str,
        *,
        wait_time: float = 0.0,
        wait_feedback_status: bool = False,
        feedback_status_command: str = "",
        feedback_answer: str = "true",
        **kwargs: Any,
    ) -> Any:
        del wait_feedback_status, feedback_status_command, feedback_answer
        self._raise_if_cancelled()
        started_at = self._clock.now()
        write_pool_log(
            self._project_path,
            self._name,
            method="GET",
            command=command,
            params=kwargs or None,
        )
        result = self._component.get(command, **kwargs)
        minimum_deadline = started_at + max(0.0, float(wait_time))
        _wait_until_sim_time(self._clock, minimum_deadline, self._stop_event)
        return result

    def _raise_if_cancelled(self) -> None:
        if self._stop_event.is_set():
            raise RunCancelledError("Run was cancelled.")


class SimPlatform(Platform):
    """Platform whose _wait() blocks on SimClock instead of real time.

    Mirrors chemunited_workflow.platform.Platform._wait(), which protocols
    call directly for a fixed delay unrelated to any specific device. Mode 1
    runs at CPU speed on SimClock, not wall-clock pace, so this busy-waits on
    simulated time instead — interruptible by the same stop_event used to
    abort a running simulation, matching the real method's cancellation-token
    behavior.
    """

    def __init__(
        self,
        components: dict[str, SimClient],
        clock: SimClock,
        stop_event: threading.Event,
    ) -> None:
        # Platform copies the mapping; SimClient intentionally provides its
        # ComponentClient-compatible command surface without HTTP behavior.
        super().__init__(cast(dict[str, ComponentClient], components))
        self._sim_clock = clock
        self._stop_event = stop_event

    def _wait(self, seconds: float) -> None:
        deadline = self._sim_clock.now() + max(0.0, float(seconds))
        _wait_until_sim_time(self._sim_clock, deadline, self._stop_event)
