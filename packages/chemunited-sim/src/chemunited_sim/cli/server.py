"""FastAPI simulation server — state machine, worker thread, workflow thread."""

from __future__ import annotations

import heapq
import queue
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from threading import Event, Thread
from typing import Any

from chemunited_workflow.platform import Platform
from chemunited_workflow.process import Process
from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from loguru import logger
from pydantic import BaseModel, Field

from ..adapter.graph import propagate_power_links, resync_component
from ..recorder.writer import Recorder
from ..visualization import (
    NoSnapshotsError,
    SnapshotReadError,
    load_latest_snapshot,
    render_dashboard_html,
    render_pyvis_html,
)
from ..worker.config import SimConfig
from ..worker.runner import Worker
from .clock import SimClock
from .loader import (
    ProjectState,
    load_project,
    parse_historical_file,
    resolve_historical_file,
)
from .sim_client import (
    SimClient,
    SimCommand,
    SimPlatform,
    iter_apply_kwargs,
    write_pool_log,
)

# ---------------------------------------------------------------------------
# State types
# ---------------------------------------------------------------------------


class SimStatus(str, Enum):
    NO_PROJECT = "no_project"
    IDLE = "idle"
    RUNNING = "running"


@dataclass
class SimulationState:
    sim_status: SimStatus
    current_t: float
    config: SimConfig
    db_path: Path | None
    project: ProjectState | None
    clock: SimClock
    cmd_queue: queue.Queue
    db_dir: Path
    log_path: Path | None = None
    _worker_thread: Thread | None = field(default=None, repr=False)
    _workflow_thread: Thread | None = field(default=None, repr=False)
    _log_sink_id: int | None = field(default=None, repr=False)
    _stop_event: Event = field(default_factory=Event, repr=False)
    _workflow_done: Event = field(default_factory=Event, repr=False)


# Module-level state (initialised by main.py before uvicorn starts)
_state: SimulationState | None = None


def get_state() -> SimulationState:
    if _state is None:
        raise RuntimeError("SimulationState not initialised")
    return _state


def _run_log_path(db_path: Path) -> Path:
    return db_path.with_name(f"{db_path.stem}_log.log")


def _detach_run_log(state: SimulationState) -> None:
    if state._log_sink_id is None:
        return
    logger.remove(state._log_sink_id)
    state._log_sink_id = None


def _attach_run_log(state: SimulationState, db_path: Path) -> None:
    _detach_run_log(state)
    log_path = _run_log_path(db_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    state._log_sink_id = logger.add(
        log_path,
        mode="w",
        encoding="utf-8",
        level="DEBUG",
        backtrace=True,
        diagnose=False,
    )
    state.log_path = log_path


# ---------------------------------------------------------------------------
# Worker thread
# ---------------------------------------------------------------------------


def _worker_thread_fn(
    db_path: Path,
    project: Any,
    clock: SimClock,
    cmd_queue: queue.Queue,
    config: SimConfig,
    stop_event: Event,
    workflow_done: Event,
    state: SimulationState,
) -> None:
    # Recorder and Worker are created here so the SQLite connection belongs
    # to this thread.
    recorder = Recorder(
        db_path=db_path,
        graph=project.graph,
        dt=config.dt,
        record_interval=2.0,
        platform_name=project.project_path.stem,
        components=project.components,
    )
    worker = Worker(
        graph=project.graph,
        components=list(project.components.values()),
        config=config,
        reactions_map=project.reactions_map,
        recorder=recorder,
    )
    components = project.components
    graph = project.graph

    scheduled: list[tuple[float, SimCommand]] = []
    power_state_cache: dict[tuple[str, int], bool] = {}
    for link in graph.power_links:
        provider = components.get(link.provider_component)
        if provider is not None:
            propagate_power_links(provider, graph, components, power_state_cache)
    wall_t0 = time.monotonic()
    sim_t0 = clock.now()

    logger.info(
        "Worker thread started | db={} dt={} t_end={}",
        db_path.name,
        config.dt,
        config.t_end,
    )

    try:
        while not stop_event.is_set():
            # 1. Drain immediate command queue
            while True:
                try:
                    cmd: SimCommand = cmd_queue.get_nowait()
                except queue.Empty:
                    break
                logger.debug(
                    "Applying command | component={} command={} kwargs={} t={:.3f}",
                    cmd.component,
                    cmd.command,
                    cmd.kwargs,
                    clock.now(),
                )
                if cmd.pre_applied:
                    resync_component(graph, components[cmd.component])
                else:
                    for call_kwargs in iter_apply_kwargs(cmd.command, cmd.kwargs):
                        result = components[cmd.component].apply(
                            cmd.command, **call_kwargs
                        )
                        for s in result.scheduled:
                            heapq.heappush(
                                scheduled,
                                (
                                    clock.now() + s.dt,
                                    SimCommand(cmd.component, s.command, s.kwargs),
                                ),
                            )
                    resync_component(graph, components[cmd.component])
                propagate_power_links(
                    components[cmd.component], graph, components, power_state_cache
                )

            # 2. Fire scheduled events that are now due
            while scheduled and scheduled[0][0] <= clock.now():
                _, sched_cmd = heapq.heappop(scheduled)
                logger.debug(
                    "Firing scheduled command | component={} command={} t={:.3f}",
                    sched_cmd.component,
                    sched_cmd.command,
                    clock.now(),
                )
                components[sched_cmd.component].apply(
                    sched_cmd.command, **sched_cmd.kwargs
                )
                resync_component(graph, components[sched_cmd.component])
                propagate_power_links(
                    components[sched_cmd.component],
                    graph,
                    components,
                    power_state_cache,
                )

            # 3. Check t_end
            if config.t_end is not None and worker.t >= config.t_end:
                logger.info(
                    "Simulation reached t_end={:.3f} — stopping worker", config.t_end
                )
                state.sim_status = SimStatus.IDLE
                return

            # 4. Auto-complete in mode 1: workflow finished + nothing pending
            if (
                not config.real_time
                and workflow_done.is_set()
                and cmd_queue.empty()
                and not scheduled
            ):
                logger.info(
                    "Workflow finished and queues empty — auto-completing at t={:.3f}",
                    worker.t,
                )
                state.sim_status = SimStatus.IDLE
                return

            # 5. Advance simulation
            worker.step()
            state.current_t = worker.t
            clock.advance(config.dt)

            # 6. Real-time throttle (mode 2)
            if config.real_time:
                elapsed_sim = clock.now() - sim_t0
                elapsed_wall = time.monotonic() - wall_t0
                drift = elapsed_sim - elapsed_wall
                if drift > 0.0:
                    time.sleep(drift)

    finally:
        recorder.close()
        logger.info("Recorder closed | final t={:.3f}", worker.t)
        if state.sim_status == SimStatus.RUNNING:
            logger.info("Worker thread exiting — marking simulation idle")
            state.sim_status = SimStatus.IDLE
        _detach_run_log(state)


# ---------------------------------------------------------------------------
# Workflow thread (mode 1 only)
# ---------------------------------------------------------------------------


def _workflow_thread_fn(
    process_sequence: list[tuple[str, dict]],
    processes: dict[str, type[Process]],
    configs: dict[str, type],
    platform: Platform,
    stop_event: Event,
    workflow_done: Event,
) -> None:
    total = len(process_sequence)
    logger.info("Workflow thread started | {} process(es) in sequence", total)
    try:
        for idx, (process_name, config_kwargs) in enumerate(process_sequence):
            if stop_event.is_set():
                logger.warning(
                    "Workflow interrupted by stop event at process {}/{} ({})",
                    idx + 1,
                    total,
                    process_name,
                )
                break
            process_cls = processes.get(process_name)
            config_cls = configs.get(process_name)
            if process_cls is None or config_cls is None:
                logger.warning(
                    "Skipping unknown process '{}' (step {}/{})",
                    process_name,
                    idx + 1,
                    total,
                )
                continue
            logger.info("Running process {}/{}: {}", idx + 1, total, process_name)
            config = config_cls(**config_kwargs)
            process = process_cls(config=config, platform=platform, process_index=idx)
            process.run_workflow(start_node="start")
            logger.info("Process {}/{} completed: {}", idx + 1, total, process_name)
    except Exception:
        logger.exception("Unhandled exception in workflow thread")
    finally:
        logger.info("Workflow thread done — signalling worker")
        workflow_done.set()


# ---------------------------------------------------------------------------
# Shared load helper (used by CLI startup + POST /project/load)
# ---------------------------------------------------------------------------


def _do_load_project(path: Path, state: SimulationState) -> None:
    logger.info("Loading project from {}", path)
    project = load_project(path)
    state.project = project
    state.sim_status = SimStatus.IDLE
    logger.info(
        "Project loaded | components={} processes={}",
        list(project.components),
        list(project.processes),
    )


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="chemunited-sim", version="0.1.0")


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/docs")


# -- Request / Response models ----------------------------------------------


class LoadProjectRequest(BaseModel):
    path: str


class StartSimRequest(BaseModel):
    execution_id: str = Field(
        description=(
            "Unique identifier for this run. Used as the filename: "
            "`<execution_id>.db`."
        )
    )
    dt: float = Field(
        default=0.1,
        description="Simulation time step in seconds.",
    )
    t_end: float | None = Field(
        default=None,
        description=(
            "Simulation end time in seconds. If null the run continues until "
            "the workflow completes (mode 1) or `POST /simulation/stop` is "
            "called (mode 2)."
        ),
    )
    real_time: bool = Field(
        default=False,
        description=(
            "False -> mode 1 (workflow simulation, CPU speed). True -> mode 2 "
            "(real-time shadow, wall-clock pace)."
        ),
    )
    historical_file: str | None = Field(
        default=None,
        description=(
            "Mode 1 only. Filename resolved inside `protocols_historic/`, or "
            "an absolute path to the JSON that defines the process sequence. "
            "If null, the most recently modified JSON in "
            "`protocols_historic/` is used."
        ),
    )


class CommandRequest(BaseModel):
    component: str
    command: str
    kwargs: dict = {}


# -- Endpoints --------------------------------------------------------------


@app.post("/project/load")
def post_project_load(req: LoadProjectRequest) -> dict:
    """Load or replace the active project.

    Compiles the hydraulic graph from `draw/setup.py` and imports the process
    classes from `protocols/__init__.py`. Accepts a project folder or a
    `.chemunited` ZIP archive. If a sibling folder with the same name as the
    ZIP exists it is used directly; otherwise the ZIP is extracted to a temp
    directory.

    - **409** if a simulation is currently running — stop it first.
    - **422** if the path does not exist or the project structure is invalid.
    """
    state = get_state()

    if state.sim_status == SimStatus.RUNNING:
        raise HTTPException(
            409, "Simulation currently running — stop it before loading a new project."
        )

    path = Path(req.path)
    try:
        _do_load_project(path, state)
    except FileNotFoundError as exc:
        raise HTTPException(422, str(exc))
    except (ValueError, AttributeError) as exc:
        raise HTTPException(422, str(exc))

    assert state.project is not None
    return {
        "status": state.sim_status.value,
        "project_path": str(state.project.project_path),
        "components": list(state.project.components),
    }


@app.get("/project")
def get_project() -> dict:
    """Return information about the currently loaded project.

    Lists every component name and every available process class. Use
    component names in `POST /simulation/command` and process names as keys
    in the historical JSON file.

    - **404** if no project has been loaded yet.
    """
    state = get_state()
    if state.project is None:
        raise HTTPException(404, "No project loaded yet.")
    return {
        "project_path": str(state.project.project_path),
        "components": list(state.project.components),
        "processes": list(state.project.processes),
    }


@app.get("/status")
def get_status() -> dict:
    """Return the full server state.

    - `sim_status`: `no_project` -> `idle` -> `running` and back to
      `idle` on stop or auto-complete.
    - `current_t`: simulation time in seconds, updated each worker step.
    - `project_loaded`: `true` once `POST /project/load` has succeeded.
    - `config`: the `SimConfig` that will be (or is being) used for the current run.
    """
    state = get_state()
    return {
        "sim_status": state.sim_status.value,
        "current_t": state.current_t,
        "project_loaded": state.project is not None,
        "config": {
            "dt": state.config.dt,
            "t_end": state.config.t_end,
            "real_time": state.config.real_time,
            "viscosity": state.config.viscosity,
        },
    }


@app.post("/simulation/start")
def post_simulation_start(req: StartSimRequest) -> dict:
    """Start a simulation run.

    **Fields:**
    - `execution_id`: name for this run, used as `<execution_id>.db`.
    - `dt`: how much simulated time passes per step, in seconds.
    - `t_end`: when to stop, in simulated seconds.
    - `real_time`: choose the simulation mode.
    - `historical_file`: protocol sequence to run in mode 1.

    **Mode 1 — Run a protocol automatically** (`real_time: false`):
    The server replays a saved protocol at full CPU speed.

    **Mode 2 — Mirror a live run** (`real_time: true`):
    The simulation keeps pace with the real instrument. Send commands via
    `POST /simulation/command`.

    The results database is created immediately and updated live.
    """
    state = get_state()

    if state.project is None or state.sim_status == SimStatus.NO_PROJECT:
        raise HTTPException(409, "No project loaded.")
    if state.sim_status == SimStatus.RUNNING:
        raise HTTPException(409, "Simulation already running.")

    project = state.project
    config = SimConfig(dt=req.dt, t_end=req.t_end, real_time=req.real_time)
    state.config = config

    # Prepare DB path. The Recorder is opened inside the worker thread.
    state.db_dir.mkdir(parents=True, exist_ok=True)
    db_path = state.db_dir / f"{req.execution_id}.db"
    state.db_path = db_path

    # Reset shared state
    while not state.cmd_queue.empty():
        try:
            state.cmd_queue.get_nowait()
        except queue.Empty:
            break
    state.clock.reset()
    state._stop_event.clear()
    state._workflow_done.clear()
    state.current_t = 0.0

    pool_dir = project.project_path / "log" / "pool"
    if pool_dir.exists():
        for f in pool_dir.glob("*.jsonl"):
            f.unlink(missing_ok=True)

    state._worker_thread = Thread(
        target=_worker_thread_fn,
        args=(
            db_path,
            project,
            state.clock,
            state.cmd_queue,
            config,
            state._stop_event,
            state._workflow_done,
            state,
        ),
        daemon=True,
    )

    if not req.real_time:
        # Mode 1: resolve historical file and build platform
        try:
            hist_path = resolve_historical_file(
                project.project_path, req.historical_file
            )
            main_parameter, process_sequence = parse_historical_file(hist_path)
        except FileNotFoundError as exc:
            raise HTTPException(422, str(exc))

        sim_platform = SimPlatform(
            {
                name: SimClient(  # type: ignore[misc]
                    name,
                    comp,
                    state.clock,
                    state.cmd_queue,
                    project.project_path,
                    state._stop_event,
                )
                for name, comp in project.components.items()
            },
            state.clock,
            state._stop_event,
        )

        state._workflow_thread = Thread(
            target=_workflow_thread_fn,
            args=(
                process_sequence,
                project.processes,
                project.configs,
                sim_platform,
                state._stop_event,
                state._workflow_done,
            ),
            daemon=True,
        )
    else:
        # Mode 2: no workflow thread; mark workflow_done so worker won't wait
        state._workflow_done.set()
        state._workflow_thread = None

    _attach_run_log(state, db_path)
    mode = "mode 2 (real-time)" if req.real_time else "mode 1 (workflow)"
    logger.info(
        "Starting simulation | {} | execution_id={} dt={} t_end={} db={}",
        mode,
        req.execution_id,
        config.dt,
        config.t_end,
        db_path.name,
    )
    state.sim_status = SimStatus.RUNNING
    state._worker_thread.start()
    if state._workflow_thread is not None:
        state._workflow_thread.start()

    return {"status": "running", "db_path": str(db_path.resolve())}


@app.post("/simulation/stop")
def post_simulation_stop() -> dict:
    """Abort the running simulation and return to idle.

    Signals the Worker Thread and Workflow Thread (if any) to stop, then waits
    up to 5 seconds for the Worker Thread to exit. The `.db` file is kept as-is
    — partial data is valid and readable.

    - **409** if no simulation is currently running.
    """
    state = get_state()
    if state.sim_status != SimStatus.RUNNING:
        raise HTTPException(409, "No simulation currently running.")
    logger.info("Stop requested — signalling worker and workflow threads")
    state._stop_event.set()
    if state._worker_thread is not None:
        state._worker_thread.join(timeout=5.0)
    logger.info("Simulation stopped at t={:.3f}", state.current_t)
    state.sim_status = SimStatus.IDLE
    return {"status": "idle"}


@app.post("/simulation/command")
def post_simulation_command(req: CommandRequest) -> dict:
    """Enqueue a component command (mode 2 — real-time only).

    The command is placed on the internal queue and applied by the Worker
    Thread at the next step boundary (between `apply()` and `step()`). Use
    this endpoint when the work-server executes a command on real hardware and
    wants to mirror it into the simulation.

    Example body:
    ```json
    {"component": "AS pump", "command": "infuse", "kwargs": {"rate": "2 ml/min"}}
    ```

    - **409** if no simulation is currently running.
    """
    state = get_state()
    if state.sim_status != SimStatus.RUNNING:
        raise HTTPException(409, "No simulation currently running.")
    assert state.project is not None
    logger.debug(
        "Command enqueued | component={} command={} kwargs={}",
        req.component,
        req.command,
        req.kwargs,
    )
    write_pool_log(
        state.project.project_path,
        req.component,
        method="PUT",
        command=req.command,
        params=req.kwargs or None,
    )
    state.cmd_queue.put(
        SimCommand(component=req.component, command=req.command, kwargs=req.kwargs)
    )
    return {"queued": True}


@app.get("/simulation/db")
def get_simulation_db() -> dict:
    """Return the absolute path of the active or last simulation database.

    The `.db` file is written in WAL mode. A GUI can open it read-only with:
    ```python
    sqlite3.connect("file:run.db?mode=ro", uri=True)
    ```

    - **404** if no simulation has been started in this server session.
    """
    state = get_state()
    if state.db_path is None:
        raise HTTPException(404, "No simulation has been run yet in this session.")
    return {"db_path": str(state.db_path.resolve())}


@app.get("/simulation/visualization")
def get_simulation_visualization() -> dict:
    """Generate and save visualization files for the latest recorded snapshot.

    Saves two files alongside the simulation database:
    - ``{stem}_graph.html`` — interactive pyvis network graph
    - ``{stem}_dashboard.html`` — time-series HTML dashboard

    Returns the absolute paths to both files.

    - **404** if no project has been loaded.
    - **404** if no simulation database has been created yet.
    - **409** if the database exists but has no recorded snapshots yet.
    - **422** if the database cannot be opened or read.
    """
    state = get_state()
    if state.project is None:
        raise HTTPException(404, "No project loaded yet.")
    if state.db_path is None or not state.db_path.exists():
        raise HTTPException(404, "No simulation database exists yet.")

    try:
        snapshot = load_latest_snapshot(state.db_path)
        graph_html = render_pyvis_html(
            graph=state.project.graph,
            components=state.project.components.values(),
            snapshot=snapshot,
        )
        dashboard_html = render_dashboard_html(
            state.db_path,
            graph=state.project.graph,
            components=state.project.components.values(),
        )
    except NoSnapshotsError as exc:
        raise HTTPException(409, str(exc)) from exc
    except SnapshotReadError as exc:
        raise HTTPException(422, str(exc)) from exc

    stem = state.db_path.stem
    folder = state.db_path.parent
    graph_path = folder / f"{stem}_graph.html"
    dashboard_path = folder / f"{stem}_dashboard.html"

    graph_path.write_text(graph_html, encoding="utf-8")
    dashboard_path.write_text(dashboard_html, encoding="utf-8")

    return {
        "graph_html": str(graph_path.resolve()),
        "dashboard_html": str(dashboard_path.resolve()),
    }
