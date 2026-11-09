"""Running a protocol: the workflow side and the physics side of one simulated run.

The server runs these on its two threads. Anything else driving a simulation can
call them the same way instead of keeping its own copies.

``run_sequence`` follows ``RunnerService._execute`` in chemunited-workflow, so a
protocol runs here as it would on the instrument: same order, same parameter
loading, and the first error stops it.
"""

from __future__ import annotations

import heapq
import queue
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from itertools import count
from typing import Any

from loguru import logger
from pydantic import BaseModel

from chemunited_core.components import ComponentData
from chemunited_core.components.live_state import iter_apply_kwargs
from chemunited_workflow import (
    Platform,
    Process,
    RunCancelledError,
    WorkflowExecutionEvent,
    WorkflowExecutor,
    WorkflowResult,
)
from chemunited_workflow.background import STOP_TIMEOUT_SECONDS, BackgroundTasks
from chemunited_workflow.compiler import compile_workflow

from ..adapter.graph import propagate_power_links, resync_component
from ..adapter.models import HydraulicGraph
from ..worker.config import SimConfig
from ..worker.runner import Worker
from .clock import SimClock
from .loader import SequenceStep
from .lockstep import Lockstep, LockstepExecutor
from .sim_client import SimCommand

# Enough that parallel branches never queue for a thread. The real runner's 4 would
# park physics behind a queued node, which can't start until a parked one finishes.
_MAX_NODE_THREADS = 32

FINISHED = "finished"
FAILED = "failed"
STOPPED = "stopped"


@dataclass(frozen=True)
class RunOutcome:
    """How a run or one of its steps ended.

    ``error`` also carries the first node error of a run that continued past it
    with ``error_resilient``, whose outcome is still ``finished``.
    """

    outcome: str
    error: str | None = None
    process: str | None = None
    node: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return asdict(self)


def run_sequence(
    sequence: Sequence[SequenceStep],
    processes: dict[str, type[Process]],
    configs: dict[str, type[BaseModel]],
    platform: Platform,
    stop_event: threading.Event,
    *,
    lockstep: Lockstep | None = None,
    historical_file: str | None = None,
    error_resilient: bool = False,
    event_listeners: Sequence[Callable[[WorkflowExecutionEvent], None]] = (),
    on_step_start: Callable[[int, SequenceStep, Any], None] | None = None,
    on_step_end: Callable[[int, SequenceStep, RunOutcome], None] | None = None,
) -> RunOutcome:
    """Run *sequence* in order until it ends, a step fails or *stop_event* is set."""
    total = len(sequence)
    background = BackgroundTasks()
    outcome = RunOutcome(FINISHED)
    logger.info("Workflow started | {} process(es) in sequence", total)
    try:
        for position, step in enumerate(sequence):
            if stop_event.is_set():
                logger.warning(
                    "Workflow stopped before process {}/{} ({})",
                    position + 1,
                    total,
                    step.key,
                )
                outcome = RunOutcome(STOPPED, process=step.key)
                break
            logger.info("Running process {}/{}: {}", position + 1, total, step.key)
            step_outcome = _run_step(
                position,
                step,
                processes,
                configs,
                platform,
                stop_event,
                background,
                lockstep,
                historical_file,
                error_resilient,
                event_listeners,
                on_step_start,
            )
            if on_step_end is not None:
                on_step_end(position, step, step_outcome)
            if step_outcome.outcome != FINISHED:
                outcome = step_outcome
                break
            logger.info("Process {}/{} completed: {}", position + 1, total, step.key)
            if step_outcome.error and outcome.error is None:
                outcome = step_outcome
    finally:
        _stop_background(background, stop_event)
    if outcome.outcome == FAILED:
        logger.error("Run failed in {}: {}", outcome.process, outcome.error)
    else:
        logger.info("Run ended: {}", outcome.outcome)
    return outcome


def _run_step(
    position: int,
    step: SequenceStep,
    processes: dict[str, type[Process]],
    configs: dict[str, type[BaseModel]],
    platform: Platform,
    stop_event: threading.Event,
    background: BackgroundTasks,
    lockstep: Lockstep | None,
    historical_file: str | None,
    error_resilient: bool,
    event_listeners: Sequence[Callable[[WorkflowExecutionEvent], None]],
    on_step_start: Callable[[int, SequenceStep, Any], None] | None,
) -> RunOutcome:
    process_cls = processes.get(step.process)
    config_cls = configs.get(step.process)
    if process_cls is None or config_cls is None:
        return RunOutcome(
            FAILED, error=f"Unknown process '{step.process}'.", process=step.key
        )

    try:
        config = config_cls.model_validate(step.params)
        process = process_cls(
            config=config, platform=platform, process_index=step.index
        )
        if historical_file is not None:
            process.load_parameters(historical_file)
        if on_step_start is not None:
            on_step_start(position, step, process.config)
        compiled = compile_workflow(process.build_workflow())
        options: dict[str, Any] = {
            "max_workers": _MAX_NODE_THREADS,
            "event_listeners": event_listeners,
            "error_resilient": error_resilient,
            "process_key": step.key,
            "cancellation_check": stop_event.is_set,
            "background": background,
        }
        executor = (
            WorkflowExecutor(compiled, **options)
            if lockstep is None
            else LockstepExecutor(compiled, lockstep=lockstep, **options)
        )
        result = executor.execute(process, start_node="start")
    except RunCancelledError:
        return RunOutcome(STOPPED, process=step.key)
    except Exception as exc:  # the executor raises on a loopback guard, among others
        logger.opt(exception=exc).error("{} failed", step.key)
        return RunOutcome(FAILED, error=str(exc), process=step.key)
    return _outcome_of(step, result, stop_event, error_resilient)


def _outcome_of(
    step: SequenceStep,
    result: WorkflowResult,
    stop_event: threading.Event,
    error_resilient: bool,
) -> RunOutcome:
    if not result.errors:
        return RunOutcome(FINISHED)
    (node, iteration), error = next(iter(result.errors.items()))
    if stop_event.is_set() or isinstance(error, RunCancelledError):
        return RunOutcome(STOPPED, process=step.key, node=node)
    message = f"{node} (iteration {iteration}): {error}"
    outcome = FINISHED if error_resilient else FAILED
    return RunOutcome(outcome, error=message, process=step.key, node=node)


def _stop_background(background: BackgroundTasks, stop_event: threading.Event) -> None:
    """Stop the background nodes, which outlive the process that started them."""
    if not background.has_tasks:
        return
    stop_event.set()
    stuck = background.join(STOP_TIMEOUT_SECONDS)
    if stuck:
        logger.warning("Background node(s) did not stop: {}", ", ".join(stuck))


def run_physics(
    worker: Worker,
    graph: HydraulicGraph,
    components: dict[str, ComponentData],
    clock: SimClock,
    commands: queue.Queue,
    config: SimConfig,
    stop_event: threading.Event,
    *,
    lockstep: Lockstep | None = None,
    after_step: Callable[[Worker], None] | None = None,
) -> None:
    """Step *worker* until the run ends. Whatever a step raises is the caller's."""
    scheduled: list[tuple[float, int, SimCommand]] = []
    order = count()
    power_state: dict[tuple[str, int], bool] = {}
    for link in graph.power_links:
        provider = components.get(link.provider_component)
        if provider is not None:
            propagate_power_links(provider, graph, components, power_state)
    wall_t0 = time.monotonic()
    sim_t0 = clock.now()

    def drain_commands() -> None:
        while True:
            try:
                command: SimCommand = commands.get_nowait()
            except queue.Empty:
                return
            logger.debug(
                "Applying command | component={} command={} kwargs={} t={:.3f}",
                command.component,
                command.command,
                command.kwargs,
                clock.now(),
            )
            component = components[command.component]
            if not command.pre_applied:
                for call_kwargs in iter_apply_kwargs(command.command, command.kwargs):
                    result = component.apply(command.command, **call_kwargs)
                    for follow_up in result.scheduled:
                        heapq.heappush(
                            scheduled,
                            (
                                clock.now() + follow_up.dt,
                                next(order),
                                SimCommand(
                                    command.component,
                                    follow_up.command,
                                    follow_up.kwargs,
                                ),
                            ),
                        )
            resync_component(graph, component)
            propagate_power_links(component, graph, components, power_state)

    while not stop_event.is_set():
        may_step = lockstep is None or lockstep.park_physics()
        drain_commands()
        if not may_step:
            return

        while scheduled and scheduled[0][0] <= clock.now():
            _, _, due = heapq.heappop(scheduled)
            logger.debug(
                "Firing scheduled command | component={} command={} t={:.3f}",
                due.component,
                due.command,
                clock.now(),
            )
            component = components[due.component]
            component.apply(due.command, **due.kwargs)
            resync_component(graph, component)
            propagate_power_links(component, graph, components, power_state)

        if config.t_end is not None and worker.t >= config.t_end:
            logger.info(
                "Simulation reached t_end={:.3f} — stopping worker", config.t_end
            )
            return

        worker.step()
        if after_step is not None:
            after_step(worker)
        # Last: this is what can wake a parked node.
        clock.advance(config.dt)
        if lockstep is not None:
            lockstep.stepped()

        if config.real_time:
            drift = (clock.now() - sim_t0) - (time.monotonic() - wall_t0)
            if drift > 0.0:
                time.sleep(drift)
