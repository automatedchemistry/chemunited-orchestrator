"""MCP tool definitions for chemunited-sim.

Lifecycle tools (project/status/run-control) call the existing FastAPI
endpoint functions in :mod:`chemunited_sim.cli.server` directly — those are
plain functions under FastAPI's route decorators — and translate a caught
``HTTPException`` into ``{"error": ...}`` instead of raising, so an LLM
client always gets a structured response. Result tools call into
:mod:`chemunited_sim.visualization` for full-run time-series data recorded
in the simulation database.
"""

from __future__ import annotations

from fastapi import HTTPException
from mcp.server.fastmcp import FastMCP

from ..cli import server as _server
from ..visualization import (
    NoSnapshotsError,
    SnapshotReadError,
    list_result_ids,
    read_edge_profile,
    read_latest_state,
    read_node_profile,
)


def _error(exc: HTTPException) -> dict:
    return {"error": exc.detail}


def register_tools(mcp: FastMCP) -> None:

    # ── Project & status ────────────────────────────────────────────────

    @mcp.tool()
    def load_project(path: str) -> dict:
        """Load or replace the active project from a directory or .chemunited ZIP.

        Rejected while a simulation is running — call ``stop_simulation``
        first. Returns the loaded project's component names.
        """
        try:
            return _server.post_project_load(_server.LoadProjectRequest(path=path))
        except HTTPException as exc:
            return _error(exc)

    @mcp.tool()
    def get_project() -> dict:
        """Return the currently loaded project's path, components, and processes."""
        try:
            return _server.get_project()
        except HTTPException as exc:
            return _error(exc)

    @mcp.tool()
    def get_status() -> dict:
        """Return the server's current state: sim_status, current_t, and config.

        ``sim_status`` is one of ``no_project``, ``idle``, or ``running``.
        Poll this after ``start_simulation`` until it reports ``idle`` before
        requesting results.
        """
        return _server.get_status()

    # ── Run control ─────────────────────────────────────────────────────

    @mcp.tool()
    def start_simulation(
        execution_id: str,
        dt: float = 0.1,
        t_end: float | None = None,
        real_time: bool = False,
        historical_file: str | None = None,
    ) -> dict:
        """Start a simulation run.

        Returns immediately — the run continues on a background thread.
        Poll ``get_status`` until ``sim_status`` is ``idle`` before calling
        any result tool.

        - ``execution_id``: name for this run; results are written to
          ``<execution_id>.db``.
        - ``dt``: simulated seconds per step.
        - ``t_end``: simulated seconds to stop at, or null to run until the
          workflow finishes (mode 1) / ``stop_simulation`` is called (mode 2).
        - ``real_time``: false runs the loaded protocol at full CPU speed
          (mode 1, the normal way to test feasibility offline); true mirrors
          a live run at wall-clock pace, driven by ``send_component_command``.
        - ``historical_file``: mode 1 only — a filename inside
          ``protocols_historic/``, or null to use the most recently modified one.
        """
        try:
            return _server.post_simulation_start(
                _server.StartSimRequest(
                    execution_id=execution_id,
                    dt=dt,
                    t_end=t_end,
                    real_time=real_time,
                    historical_file=historical_file,
                )
            )
        except HTTPException as exc:
            return _error(exc)

    @mcp.tool()
    def stop_simulation() -> dict:
        """Abort the running simulation and return to idle.

        The database is kept as-is — partial results remain readable via
        the result tools.
        """
        try:
            return _server.post_simulation_stop()
        except HTTPException as exc:
            return _error(exc)

    @mcp.tool()
    def send_component_command(
        component: str,
        command: str,
        kwargs: dict | None = None,
    ) -> dict:
        """Enqueue a component command during a real-time (mode 2) run.

        Use this to mirror a command executed on real hardware into the
        simulation. Has no effect in mode 1, which replays a protocol
        automatically.
        """
        try:
            return _server.post_simulation_command(
                _server.CommandRequest(
                    component=component,
                    command=command,
                    kwargs=kwargs or {},
                )
            )
        except HTTPException as exc:
            return _error(exc)

    # ── Results & analysis ──────────────────────────────────────────────

    @mcp.tool()
    def list_result_series() -> dict:
        """List the node/edge identifiers recorded in the current run's database.

        Use the returned ``nodes``/``edges`` identifiers with
        ``get_node_profile``/``get_edge_profile``. A vessel's inventory node
        is named ``"<component_name>.Inventory"``.
        """
        state = _server.get_state()
        if state.db_path is None or not state.db_path.exists():
            return {"error": "No simulation database exists yet."}
        try:
            return list_result_ids(state.db_path)
        except (NoSnapshotsError, SnapshotReadError) as exc:
            return {"error": str(exc)}

    @mcp.tool()
    def get_latest_state() -> dict:
        """Return a cross-sectional snapshot at the most recently recorded time.

        Includes every node's pressure, every edge's flow, and each
        inventory's temperature and phase content. Use this for a quick
        "where do things stand right now" feasibility check.
        """
        state = _server.get_state()
        if state.db_path is None or not state.db_path.exists():
            return {"error": "No simulation database exists yet."}
        try:
            return read_latest_state(state.db_path)
        except (NoSnapshotsError, SnapshotReadError) as exc:
            return {"error": str(exc)}

    @mcp.tool()
    def get_node_profile(node_id: str, tail: int | None = None) -> dict:
        """Return the full-run time series for one node.

        Includes pressure, temperature, and per-phase species content
        (moles). Use ``list_result_series`` first to find valid node
        identifiers. Pass ``tail`` to return only the last N recorded
        points on long runs.
        """
        state = _server.get_state()
        if state.db_path is None or not state.db_path.exists():
            return {"error": "No simulation database exists yet."}
        try:
            return read_node_profile(state.db_path, node_id, tail=tail)
        except (NoSnapshotsError, SnapshotReadError) as exc:
            return {"error": str(exc)}

    @mcp.tool()
    def get_edge_profile(edge_id: str, tail: int | None = None) -> dict:
        """Return the full-run time series for one edge.

        Includes flow rate and average cell temperature where recorded. Use
        ``list_result_series`` first to find valid edge identifiers. Pass
        ``tail`` to return only the last N recorded points on long runs.
        """
        state = _server.get_state()
        if state.db_path is None or not state.db_path.exists():
            return {"error": "No simulation database exists yet."}
        try:
            return read_edge_profile(state.db_path, edge_id, tail=tail)
        except (NoSnapshotsError, SnapshotReadError) as exc:
            return {"error": str(exc)}

    # ── Human-facing outputs ────────────────────────────────────────────

    @mcp.tool()
    def get_simulation_db() -> dict:
        """Return the absolute path of the active or last simulation database."""
        try:
            return _server.get_simulation_db()
        except HTTPException as exc:
            return _error(exc)

    @mcp.tool()
    def get_simulation_visualization() -> dict:
        """Render and save the interactive graph + dashboard HTML files.

        Covers the latest recorded snapshot; returns their absolute paths.
        For the LLM's own analysis prefer ``get_latest_state``/
        ``get_node_profile``/``get_edge_profile`` — this is for pointing a
        human user at a visual report.
        """
        try:
            return _server.get_simulation_visualization()
        except HTTPException as exc:
            return _error(exc)
