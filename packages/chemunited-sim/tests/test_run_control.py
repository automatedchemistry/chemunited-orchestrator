"""A run's workflow and physics take turns, and the first error stops the run."""

from __future__ import annotations

import queue
import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import networkx as nx
import pytest
from loguru import logger
from pydantic import BaseModel, ConfigDict

from chemunited_core.common.enums import ConnectionType
from chemunited_core.connections import EdgeData, EdgeMode
from chemunited_core.figure_registry import COMPONENTS
from chemunited_quantities import ChemUnitQuantity
from chemunited_sim.adapter import compile_graph
from chemunited_sim.cli.clock import SimClock
from chemunited_sim.cli.loader import SequenceStep
from chemunited_sim.cli.lockstep import Lockstep
from chemunited_sim.cli.run import (
    FAILED,
    FINISHED,
    STOPPED,
    RunOutcome,
    run_physics,
    run_sequence,
)
from chemunited_sim.cli.sim_client import SimClient, SimPlatform
from chemunited_sim.worker import SimConfig, Worker
from chemunited_workflow import (
    NodeExecutionContext,
    Process,
    RunCancelledError,
    WorkflowEdgeSpec,
    WorkflowNodeSpec,
)

DT = 0.1
CONDITION = WorkflowEdgeSpec(condition=True).model_dump(exclude_none=True)


class Config(BaseModel):
    model_config = ConfigDict(frozen=True)


def _make(figure: str, name: str, **kwargs):
    definition = COMPONENTS[figure]
    return definition.data_class.from_mode(definition.mode_class(name=name, **kwargs))


def _tube(origin: str, origin_port: int, destination: str, port: int) -> EdgeData:
    return EdgeData.from_mode(
        EdgeMode(
            name=f"{origin}_{origin_port}_{destination}_{port}",
            origin=origin,
            origin_port=origin_port,
            destination=destination,
            destination_port=port,
            classification=ConnectionType.HYDRAULIC,
            length="100 mm",
            diameter="1 mm",
        )
    )


@dataclass
class Rig:
    """A bottle pushed by argon through a valve into a vented vessel."""

    clock: SimClock
    stop: threading.Event
    commands: queue.Queue
    lockstep: Lockstep
    platform: SimPlatform
    worker: Worker
    graph: object
    components: dict
    log: list = field(default_factory=list)

    def received_ml(self) -> float:
        return self.worker.inv_states["receiver.Inventory"].liq_volume * 1e6


def _rig(tmp_path, stall_seconds: float = 60.0) -> Rig:
    argon = _make("Source", "argon", setpoint=ChemUnitQuantity("1.2 bar"))
    bottle = _make(
        "GlassBottle",
        "bottle",
        capacity=ChemUnitQuantity("100 ml"),
        top_access=1,
        bottom_access=1,
        pressure_access=True,
    )
    bottle.internal_inventory.liq_content.volume = 80.0e-6
    bottle.internal_inventory.liq_content.initial_species = {"water": 4.0}
    bottle.internal_inventory.gas_content.volume = 20.0e-6
    bottle.internal_inventory.gas_content.initial_species = {"air": 8.0e-4}
    valve = _make("SolenoidValve", "valve")
    receiver = _make("GlassBottle", "receiver", capacity=ChemUnitQuantity("100 ml"))
    listed = [argon, bottle, valve, receiver]
    graph = compile_graph(
        listed,
        [
            _tube("argon", 1, "bottle", 1),
            _tube("bottle", 2, "valve", 1),
            _tube("valve", 2, "receiver", 1),
        ],
    )
    components = {component.name: component for component in listed}
    clock = SimClock()
    stop = threading.Event()
    commands: queue.Queue = queue.Queue()
    lockstep = Lockstep(clock, stop, stall_seconds=stall_seconds)
    clock.lockstep = lockstep
    platform = SimPlatform(
        {
            name: SimClient(name, component, clock, commands, tmp_path, stop)
            for name, component in components.items()
        },
        clock,
        stop,
    )
    worker = Worker(graph, listed, SimConfig(dt=DT))
    return Rig(clock, stop, commands, lockstep, platform, worker, graph, components)


def _run(rig: Rig, sequence, processes, configs, **options) -> RunOutcome:
    """Run the workflow on a thread and physics here, as the server does."""
    results: list[RunOutcome] = []

    def workflow() -> None:
        try:
            results.append(
                run_sequence(
                    sequence,
                    processes,
                    configs,
                    rig.platform,
                    rig.stop,
                    lockstep=rig.lockstep,
                    **options,
                )
            )
        finally:
            rig.lockstep.finish()

    thread = threading.Thread(target=workflow, daemon=True)
    thread.start()
    run_physics(
        rig.worker,
        rig.graph,
        rig.components,
        rig.clock,
        rig.commands,
        SimConfig(dt=DT),
        rig.stop,
        lockstep=rig.lockstep,
    )
    thread.join(timeout=20.0)
    assert not thread.is_alive()
    return results[0]


def _linear(*names: str) -> nx.DiGraph:
    return _branches([list(names)])


def _branches(branches: list[list[str]]) -> nx.DiGraph:
    """start, then each branch in parallel. Nodes run the method of their name."""
    graph = nx.DiGraph()

    def add(name: str) -> None:
        graph.add_node(
            name,
            **WorkflowNodeSpec(node_id=name, method=name).model_dump(exclude_none=True),
        )

    add("start")
    for branch in branches:
        previous = "start"
        for name in branch:
            add(name)
            graph.add_edge(previous, name, **CONDITION)
            previous = name
    return graph


def _step(process: str = "Test", index: int = 0) -> SequenceStep:
    return SequenceStep(process, index, {})


def _one_process(cls: type[Process]) -> dict:
    return {"processes": {"Test": cls}, "configs": {"Test": Config}}


def _jitter() -> None:
    """Python taking its time between commands, which physics must not exploit."""
    time.sleep(random.uniform(0.0, 0.02))


# ---------------------------------------------------------------------------
# Lockstep
# ---------------------------------------------------------------------------


def test_physics_waits_for_a_waiter_and_for_it_to_come_due() -> None:
    clock = SimClock()
    stop = threading.Event()
    lockstep = Lockstep(clock, stop, stall_seconds=5.0)
    answers: list[bool] = []
    physics = threading.Thread(target=lambda: answers.append(lockstep.park_physics()))
    physics.start()
    time.sleep(0.05)
    assert physics.is_alive()  # nobody is parked yet

    waiter = threading.Thread(target=lockstep.wait_until, args=(1.0,))
    waiter.start()
    physics.join(timeout=2.0)
    assert answers == [True]

    clock.advance(1.0)
    lockstep.stepped()
    waiter.join(timeout=2.0)
    assert not waiter.is_alive()


def test_physics_holds_off_while_a_due_waiter_has_not_woken() -> None:
    clock = SimClock()
    lockstep = Lockstep(clock, threading.Event())
    lockstep._waiters[1] = 1.0
    assert lockstep._may_step()

    clock.advance(1.0)

    assert not lockstep._may_step()


def test_physics_holds_off_while_some_running_node_is_not_parked() -> None:
    clock = SimClock()
    lockstep = Lockstep(clock, threading.Event())
    lockstep._running_nodes.update({("p", ("a", 0)), ("p", ("b", 0))})
    lockstep._waiters[1] = 1.0
    assert not lockstep._may_step()

    lockstep._waiters[2] = 2.0

    assert lockstep._may_step()


def test_physics_holds_off_during_a_hold() -> None:
    clock = SimClock()
    lockstep = Lockstep(clock, threading.Event())
    lockstep._waiters[1] = 1.0

    with lockstep.hold():
        assert not lockstep._may_step()

    assert lockstep._may_step()


def test_finish_and_stop_end_physics() -> None:
    lockstep = Lockstep(SimClock(), threading.Event())
    lockstep.finish()
    assert lockstep.park_physics() is False

    stop = threading.Event()
    stop.set()
    assert Lockstep(SimClock(), stop).park_physics() is False


def test_stop_wakes_a_parked_node_with_a_cancellation() -> None:
    stop = threading.Event()
    lockstep = Lockstep(SimClock(), stop)
    errors: list[BaseException] = []

    def wait() -> None:
        try:
            lockstep.wait_until(1.0e6)
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=wait)
    thread.start()
    time.sleep(0.05)
    stop.set()
    thread.join(timeout=2.0)

    assert not thread.is_alive()
    assert isinstance(errors[0], RunCancelledError)


def test_time_stands_still_while_a_node_runs_and_waits_are_exact(tmp_path) -> None:
    rig = _rig(tmp_path)
    readings: list[float] = []

    class Timed(Process[Config]):
        def build_workflow(self) -> nx.DiGraph:
            return _linear("work", "more")

        def start(self, _ctx: NodeExecutionContext) -> bool:
            return True

        def work(self, _ctx: NodeExecutionContext) -> bool:
            readings.append(rig.clock.now())
            time.sleep(0.2)  # would be several steps of free-running physics
            readings.append(rig.clock.now())
            self.platform._wait(1.0)
            readings.append(rig.clock.now())
            return True

        def more(self, _ctx: NodeExecutionContext) -> bool:
            readings.append(rig.clock.now())
            self.platform._wait(0.3)
            readings.append(rig.clock.now())
            return True

    outcome = _run(rig, [_step()], **_one_process(Timed))

    assert outcome == RunOutcome(FINISHED)
    assert readings[0] == 0.0
    assert readings[1] == 0.0
    assert readings[2] == pytest.approx(1.0, abs=1e-6)
    # Moving to the next node takes no simulated time.
    assert readings[3] == readings[2]
    assert readings[4] == pytest.approx(1.3, abs=1e-6)


def _pulsed_run(tmp_path) -> tuple[float, float]:
    rig = _rig(tmp_path)

    class Pulsed(Process[Config]):
        def build_workflow(self) -> nx.DiGraph:
            return _linear("pulse")

        def start(self, _ctx: NodeExecutionContext) -> bool:
            return True

        def pulse(self, _ctx: NodeExecutionContext) -> bool:
            for _ in range(5):
                self.platform["valve"].put("open")
                _jitter()
                self.platform._wait(0.3)
                _jitter()
                self.platform["valve"].put("close")
                _jitter()
                self.platform._wait(0.2)
            return True

    assert _run(rig, [_step()], **_one_process(Pulsed)).outcome == FINISHED
    return rig.received_ml(), rig.worker.t


def test_repeat_runs_are_identical_to_the_last_digit(tmp_path) -> None:
    first = _pulsed_run(tmp_path)
    second = _pulsed_run(tmp_path)
    third = _pulsed_run(tmp_path)

    assert first == second == third
    assert first[1] == pytest.approx(2.5, abs=DT)


def _parallel_run(tmp_path, branches: int) -> list[tuple[str, float]]:
    rig = _rig(tmp_path)
    log: list[tuple[str, float]] = []
    lock = threading.Lock()

    def note(label: str) -> None:
        with lock:
            log.append((label, rig.clock.now()))

    def make_node(index: int, seconds: float) -> Callable:
        def node(self, _ctx: NodeExecutionContext) -> bool:
            _jitter()
            note(f"{index} starts")
            self.platform._wait(seconds)
            note(f"{index} ends")
            _jitter()
            return True

        return node

    names = [f"branch_{index}" for index in range(branches)]
    next_names = [f"then_{index}" for index in range(branches)]
    attributes = {"build_workflow": None, "start": lambda self, _ctx: True}
    for index, name in enumerate(names):
        attributes[name] = make_node(index, 0.3 + 0.2 * index)
        attributes[next_names[index]] = make_node(100 + index, 0.5)
    attributes["build_workflow"] = lambda self: _branches(
        [[first, then] for first, then in zip(names, next_names, strict=True)]
    )
    Parallel = type("Parallel", (Process,), attributes)

    assert _run(rig, [_step()], **_one_process(Parallel)).outcome == FINISHED
    return sorted(log)


def test_parallel_branches_keep_exact_time_and_repeat(tmp_path) -> None:
    first = _parallel_run(tmp_path, branches=2)
    second = _parallel_run(tmp_path, branches=2)

    assert first == second
    times = dict(first)
    assert times["0 starts"] == 0.0
    assert times["0 ends"] == pytest.approx(0.3, abs=1e-6)
    assert times["1 ends"] == pytest.approx(0.5, abs=1e-6)
    assert times["100 starts"] == times["0 ends"]
    assert times["100 ends"] == pytest.approx(0.8, abs=1e-6)
    assert times["101 ends"] == pytest.approx(1.0, abs=1e-6)


def test_more_parallel_branches_than_the_real_runners_pool_still_step(
    tmp_path,
) -> None:
    started = time.monotonic()

    log = _parallel_run(tmp_path, branches=6)

    assert time.monotonic() - started < 30.0  # no stall fallback
    assert dict(log)["5 ends"] == pytest.approx(1.3, abs=1e-6)


def test_a_node_that_sleeps_falls_back_to_free_running_once(tmp_path) -> None:
    rig = _rig(tmp_path, stall_seconds=0.2)
    messages: list[str] = []
    sink = logger.add(lambda m: messages.append(m.record["message"]), level="WARNING")

    class Sleeper(Process[Config]):
        def build_workflow(self) -> nx.DiGraph:
            return _linear("poll")

        def start(self, _ctx: NodeExecutionContext) -> bool:
            return True

        def poll(self, _ctx: NodeExecutionContext) -> bool:
            # Only ends if physics moves on without this node parking.
            deadline = time.monotonic() + 15.0
            while rig.clock.now() < 1.0:
                assert time.monotonic() < deadline
                time.sleep(0.01)
            return True

    try:
        outcome = _run(rig, [_step()], **_one_process(Sleeper))
    finally:
        logger.remove(sink)

    assert outcome.outcome == FINISHED
    assert rig.lockstep.free_running
    assert len([m for m in messages if "without a simulated wait" in m]) == 1


def test_background_node_runs_alongside_and_stops_with_the_run(tmp_path) -> None:
    rig = _rig(tmp_path)
    ticks: list[float] = []
    stopped: list[bool] = []

    class WithBackground(Process[Config]):
        def build_workflow(self) -> nx.DiGraph:
            graph = _linear("work")
            graph.add_node(
                "monitor",
                **WorkflowNodeSpec(node_id="monitor", method="monitor").model_dump(
                    exclude_none=True
                ),
                block_tag="background",
            )
            graph.add_edge("start", "monitor", **CONDITION)
            return graph

        def start(self, _ctx: NodeExecutionContext) -> bool:
            return True

        def work(self, _ctx: NodeExecutionContext) -> bool:
            self.platform._wait(1.0)
            return True

        def monitor(self, _ctx: NodeExecutionContext) -> bool:
            try:
                while True:
                    ticks.append(rig.clock.now())
                    self.platform._wait(0.3)
            except RunCancelledError:
                stopped.append(True)
                raise

    outcome = _run(rig, [_step()], **_one_process(WithBackground))

    assert outcome.outcome == FINISHED
    assert stopped == [True]
    assert len(ticks) >= 3
    assert ticks[1] == pytest.approx(0.3, abs=1e-6)


def test_a_full_stroke_empties_the_syringe_in_exactly_the_right_time(tmp_path) -> None:
    pump = _make(
        "SyringePump",
        "pump",
        syringe_volume=ChemUnitQuantity("5 ml"),
        syringe_actual_volume=ChemUnitQuantity("1 ml"),
    )
    pump.internal_inventory.liq_content.volume = 1.0e-6
    pump.internal_inventory.liq_content.initial_species = {"water": 0.05}
    sink = _make("PressureControl", "sink")
    listed = [pump, sink]
    graph = compile_graph(listed, [_tube("pump", 1, "sink", 1)])
    components = {component.name: component for component in listed}
    clock = SimClock()
    stop = threading.Event()
    commands: queue.Queue = queue.Queue()
    lockstep = Lockstep(clock, stop)
    clock.lockstep = lockstep
    platform = SimPlatform(
        {
            name: SimClient(name, component, clock, commands, tmp_path, stop)
            for name, component in components.items()
        },
        clock,
        stop,
    )
    worker = Worker(graph, listed, SimConfig(dt=DT))
    rig = Rig(clock, stop, commands, lockstep, platform, worker, graph, components)
    readings: list[float] = []

    class Stroke(Process[Config]):
        def build_workflow(self) -> nx.DiGraph:
            return _linear("stroke")

        def start(self, _ctx: NodeExecutionContext) -> bool:
            return True

        def stroke(self, _ctx: NodeExecutionContext) -> bool:
            self.platform["pump"].put("infuse", rate="60 ml/min", volume="0.4 ml")
            readings.append(clock.now())
            self.platform["pump"].put("infuse-all")
            readings.append(clock.now())
            return True

    outcome = _run(rig, [_step()], **_one_process(Stroke))

    assert outcome.outcome == FINISHED
    assert readings[0] == pytest.approx(0.4, abs=1e-6)
    # The other 0.6 mL at the same 60 mL/min.
    assert readings[1] == pytest.approx(1.0, abs=1e-6)
    assert pump.flow_rate_si == 0.0
    state = worker.inv_states["pump.Inventory"]
    assert state.liq_volume == pytest.approx(0.0, abs=1e-9)
    assert pump.fill_m3 == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# Failures
# ---------------------------------------------------------------------------


class Fails(Process[Config]):
    def build_workflow(self) -> nx.DiGraph:
        return _linear("boom", "after")

    def start(self, _ctx: NodeExecutionContext) -> bool:
        return True

    def boom(self, _ctx: NodeExecutionContext) -> bool:
        raise ValueError("the reagent line is blocked")

    def after(self, _ctx: NodeExecutionContext) -> bool:
        return True


def _recording_process(ran: list[int]) -> type[Process]:
    class Recorded(Process[Config]):
        def build_workflow(self) -> nx.DiGraph:
            return _linear("work")

        def start(self, _ctx: NodeExecutionContext) -> bool:
            return True

        def work(self, _ctx: NodeExecutionContext) -> bool:
            ran.append(self.process_index)
            return True

    return Recorded


def test_a_failed_node_stops_the_sequence_and_says_where(tmp_path) -> None:
    rig = _rig(tmp_path)
    ran: list[int] = []

    outcome = _run(
        rig,
        [_step("Fails", 0), _step("Next", 1)],
        processes={"Fails": Fails, "Next": _recording_process(ran)},
        configs={"Fails": Config, "Next": Config},
    )

    assert outcome.outcome == FAILED
    assert outcome.process == "Fails_0"
    assert outcome.node == "boom"
    assert "the reagent line is blocked" in outcome.error
    assert ran == []


def test_error_resilient_carries_on_and_remembers_the_error(tmp_path) -> None:
    rig = _rig(tmp_path)
    ran: list[int] = []

    outcome = _run(
        rig,
        [_step("Fails", 0), _step("Next", 7)],
        processes={"Fails": Fails, "Next": _recording_process(ran)},
        configs={"Fails": Config, "Next": Config},
        error_resilient=True,
    )

    assert outcome.outcome == FINISHED
    assert "the reagent line is blocked" in outcome.error
    assert ran == [7]


def test_steps_run_with_the_index_from_their_key(tmp_path) -> None:
    rig = _rig(tmp_path)
    ran: list[int] = []

    outcome = _run(
        rig,
        [_step("Next", 5), _step("Next", 2)],
        processes={"Next": _recording_process(ran)},
        configs={"Next": Config},
    )

    assert outcome.outcome == FINISHED
    assert ran == [5, 2]


def test_an_unknown_process_fails_the_run(tmp_path) -> None:
    rig = _rig(tmp_path)

    outcome = _run(rig, [_step("Missing", 3)], processes={}, configs={})

    assert outcome.outcome == FAILED
    assert outcome.process == "Missing_3"
    assert "Unknown process 'Missing'" in outcome.error


def test_invalid_parameters_fail_the_run(tmp_path) -> None:
    class Strict(BaseModel):
        amount: int

    rig = _rig(tmp_path)

    outcome = _run(
        rig,
        [SequenceStep("Test", 0, {"amount": "lots"})],
        processes={"Test": Fails},
        configs={"Test": Strict},
    )

    assert outcome.outcome == FAILED
    assert "amount" in outcome.error


def test_a_loopback_guard_fails_the_run(tmp_path) -> None:
    class Looping(Process[Config]):
        def build_workflow(self) -> nx.DiGraph:
            graph = _linear("again")
            graph.add_edge(
                "again", "again", loopback=True, trigger_on=True, max_iterations=2
            )
            return graph

        def start(self, _ctx: NodeExecutionContext) -> bool:
            return True

        def again(self, _ctx: NodeExecutionContext) -> bool:
            return True

    rig = _rig(tmp_path)

    outcome = _run(rig, [_step()], **_one_process(Looping))

    assert outcome.outcome == FAILED
    assert "max_iterations=2" in outcome.error


def test_a_stop_ends_the_run_as_stopped(tmp_path) -> None:
    rig = _rig(tmp_path)
    ran: list[int] = []

    class Long(Process[Config]):
        def build_workflow(self) -> nx.DiGraph:
            return _linear("wait")

        def start(self, _ctx: NodeExecutionContext) -> bool:
            return True

        def wait(self, _ctx: NodeExecutionContext) -> bool:
            self.platform._wait(1.0e6)
            return True

    threading.Timer(0.2, rig.stop.set).start()

    outcome = _run(
        rig,
        [_step("Long", 0), _step("Next", 1)],
        processes={"Long": Long, "Next": _recording_process(ran)},
        configs={"Long": Config, "Next": Config},
    )

    assert outcome.outcome == STOPPED
    assert outcome.process == "Long_0"
    assert ran == []


def test_steps_report_their_start_and_end(tmp_path) -> None:
    rig = _rig(tmp_path)
    ran: list[int] = []
    seen: list[tuple] = []

    outcome = _run(
        rig,
        [_step("Next", 4), _step("Fails", 5)],
        processes={"Next": _recording_process(ran), "Fails": Fails},
        configs={"Next": Config, "Fails": Config},
        on_step_start=lambda position, step, config: seen.append(
            ("start", position, step.key, type(config).__name__)
        ),
        on_step_end=lambda position, step, result: seen.append(
            ("end", position, step.key, result.outcome)
        ),
    )

    assert outcome.outcome == FAILED
    assert seen == [
        ("start", 0, "Next_4", "Config"),
        ("end", 0, "Next_4", FINISHED),
        ("start", 1, "Fails_5", "Config"),
        ("end", 1, "Fails_5", FAILED),
    ]


def test_run_physics_lets_a_failure_reach_its_caller(tmp_path) -> None:
    rig = _rig(tmp_path)

    def broken() -> None:
        raise RuntimeError("the solver blew up")

    rig.worker.step = broken
    rig.lockstep._waiters[1] = 1.0e6

    with pytest.raises(RuntimeError, match="the solver blew up"):
        run_physics(
            rig.worker,
            rig.graph,
            rig.components,
            rig.clock,
            rig.commands,
            SimConfig(dt=DT),
            rig.stop,
            lockstep=rig.lockstep,
        )
