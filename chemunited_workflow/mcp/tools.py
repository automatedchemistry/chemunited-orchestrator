"""MCP tool definitions for chemunited."""

from __future__ import annotations

import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from chemunited_workflow.api.project_holder import ProjectHolder
from chemunited_workflow.api.services.custom_routes import (
    call_custom_route as _call_custom_route,
    discover_custom_routes as _discover_custom_routes,
)
from chemunited_workflow.api.services.monitoring import MonitoringService
from chemunited_workflow.api.services.protocol import ProtocolService
from chemunited_workflow.api.services.runner import RunnerService
from chemunited_workflow.exceptions import MonitoringRunActiveError
from chemunited_workflow.project_loader import (
    ProjectLoadError,
    format_broken_project_error,
    load_project as _load_project,
)

_NO_PROJECT = "No project loaded. Use the load_project tool first."


def _protocol(holder: ProjectHolder) -> ProtocolService:
    svc = holder.protocol_service
    if svc is None:
        raise RuntimeError(
            "protocol_service is None — call is_loaded() before _protocol()"
        )
    return svc


def _runner(holder: ProjectHolder) -> RunnerService:
    svc = holder.runner_service
    if svc is None:
        raise RuntimeError("runner_service is None — call is_loaded() before _runner()")
    return svc


def _monitoring(holder: ProjectHolder) -> MonitoringService:
    svc = holder.monitoring_service
    if svc is None:
        raise RuntimeError(
            "monitoring_service is None — call is_loaded() before _monitoring()"
        )
    return svc


def _project_dir(holder: ProjectHolder) -> Path:
    pd = holder.project_dir
    if pd is None:
        raise RuntimeError(
            "project_dir is None — call is_loaded() before _project_dir()"
        )
    return pd


def register_tools(mcp: FastMCP, holder: ProjectHolder) -> None:

    # ── Project management ────────────────────────────────────────────────────

    @mcp.tool()
    def load_project(project_dir: str) -> dict:
        """Load or switch the active project from a directory path.

        The directory must contain ``protocols/__init__.py`` (exporting
        ``PROCESSES`` and ``CONFIGS``) and ``protocols/main_parameters.py``
        (exporting ``MainParameter``). Switching is rejected if a run is
        currently active.

        Parameters
        ----------
        project_dir:
            Absolute or relative path to the project root directory.
        """
        active = holder.active_run_id()
        if active is not None:
            return {"error": f"Cannot switch project while run '{active}' is active."}
        project_path = Path(project_dir).resolve()
        try:
            modules = _load_project(project_path)
        except ProjectLoadError as exc:
            return {"error": str(exc)}
        try:
            holder.load(modules)
        except Exception as exc:
            return {
                "error": format_broken_project_error(
                    exc,
                    project_path,
                    f"Failed to initialize services for project '{project_path}'",
                )
            }
        return {"project_dir": str(holder.project_dir)}

    @mcp.tool()
    def get_project() -> dict:
        """Return the currently loaded project directory, or null if none is loaded."""
        pd = holder.project_dir
        return {"project_dir": str(pd) if pd is not None else None}

    # ── Processes ─────────────────────────────────────────────────────────────

    @mcp.tool()
    def list_processes() -> list[dict]:
        """List all processes registered in this experiment with their parameter
        schemas. Call this first to discover what processes are available before
        building a snapshot."""
        if not holder.is_loaded():
            return [{"error": _NO_PROJECT}]
        return _protocol(holder).list_processes()

    @mcp.tool()
    def get_process_schema(name: str) -> dict:
        """Return the full parameter schema for a named process, including
        ProcessConfig fields and MainParameter fields. Field metadata includes
        ``group``, ``editable``, and ``visible`` from ``json_schema_extra``."""
        if not holder.is_loaded():
            return {"error": _NO_PROJECT}
        return _protocol(holder).get_process_schema(name)

    # ── Protocols ─────────────────────────────────────────────────────────────

    @mcp.tool()
    def list_protocols() -> list[dict]:
        """List all protocols in protocols_historic/, most recent first."""
        if not holder.is_loaded():
            return [{"error": _NO_PROJECT}]
        return _protocol(holder).list_protocols()

    @mcp.tool()
    def get_protocol(filename: str) -> dict:
        """Read the full contents of a specific protocol JSON file."""
        if not holder.is_loaded():
            return {"error": _NO_PROJECT}
        return _protocol(holder).read_protocol(filename)

    @mcp.tool()
    def create_protocol(name: str, data: dict) -> dict:
        """Validate and save a new protocol file. Each call always creates a
        new versioned file — protocols are immutable once written.

        Parameters
        ----------
        name:
            Short name, e.g. ``"suzuki_batch_14"``. The saved filename will be
            ``{name}_{timestamp}.json``.
        data:
            Full protocol dict. Must contain ``"main_parameter"`` and one key per
            process step in ``"{process_name}_{index}"`` format, in execution order.
        """
        if not holder.is_loaded():
            return {"error": _NO_PROJECT}
        filename = _protocol(holder).write_protocol(name, data)
        return {"filename": filename}

    @mcp.tool()
    def delete_protocol(filename: str) -> dict:
        """Permanently delete a protocol file from ``protocols_historic/``.

        This action is irreversible. Use ``list_protocols`` to discover filenames.
        """
        if not holder.is_loaded():
            return {"error": _NO_PROJECT}
        try:
            _protocol(holder).delete_protocol(filename)
            return {"deleted": filename}
        except FileNotFoundError as exc:
            return {"error": str(exc)}

    # ── Run control ───────────────────────────────────────────────────────────

    @mcp.tool()
    def start_run(
        protocol: str, dry_run: bool = False, record_monitoring: bool = False
    ) -> dict:
        """Start executing a protocol in the background.
        Returns a ``run_id`` to poll with ``get_run_status``.

        Parameters
        ----------
        protocol:
            Filename in ``protocols_historic/``.
        dry_run:
            When ``True``, all HTTP calls to devices are suppressed and the
            workflow runs in simulation mode.
        record_monitoring:
            When ``True``, monitoring is forced on for the run's duration and
            every reading is persisted to ``log/monitoring/{run_id}/``, using
            whatever variables are currently registered via
            ``set_monitoring_config``. Returns an error and never starts the
            run if no monitoring variables are registered.
        """
        if not holder.is_loaded():
            return {"error": _NO_PROJECT}
        try:
            run_id = _runner(holder).start(
                protocol, dry_run=dry_run, record_monitoring=record_monitoring
            )
        except ValueError as exc:
            return {"error": str(exc)}
        return {"run_id": run_id}

    @mcp.tool()
    def get_run_status() -> dict:
        """Poll the status of the current execution.
        Returns the current state (``running``, ``paused``, ``finished``,
        ``failed``, or ``cancelled``) and all events since the last call to
        this tool. Call repeatedly until ``state`` is ``"finished"`` or
        ``"failed"``."""
        if not holder.is_loaded():
            return {"error": _NO_PROJECT}
        rec = holder.run_store.get()
        if rec is None:
            return {"error": "No run is active or recorded."}
        events = holder.run_store.pop_events()
        return {
            "run_id": rec.run_id,
            "state": rec.state.value,
            "events": [e.model_dump() for e in events],
        }

    @mcp.tool()
    def get_run_report() -> dict:
        """Return the full execution report for the current or last completed run.
        Returns one WorkflowResult per process step, in execution order."""
        if not holder.is_loaded():
            return {"error": _NO_PROJECT}
        rec = holder.run_store.get()
        if rec is None:
            return {"error": "No run is active or recorded."}
        return {
            "run_id": rec.run_id,
            "state": rec.state.value,
            "results": [r.model_dump() for r in rec.results],
        }

    @mcp.tool()
    def cancel_run() -> dict:
        """Cancel the active run and signal clients to stop cooperatively.
        Works whether the run is currently ``running`` or ``paused``."""
        if not holder.is_loaded():
            return {"error": _NO_PROJECT}
        ok = holder.run_store.cancel()
        return {"cancelled": ok}

    @mcp.tool()
    def pause_run() -> dict:
        """Pause the active run.

        Sends a cooperative pause signal. Execution holds at the next
        checkpoint — which may be between individual device calls inside a
        node, not just between nodes — then blocks until resumed or
        cancelled. The physical hardware is left in whatever state it
        reached; nothing is moved to a "safe" position. Only valid while the
        run is ``running``.
        """
        if not holder.is_loaded():
            return {"error": _NO_PROJECT}
        ok = holder.run_store.pause()
        return {"paused": ok}

    @mcp.tool()
    def resume_run() -> dict:
        """Resume a paused run, continuing execution from exactly where it held.
        Only valid while the run is ``paused``."""
        if not holder.is_loaded():
            return {"error": _NO_PROJECT}
        ok = holder.run_store.resume()
        return {"resumed": ok}

    # ── Process source ────────────────────────────────────────────────────────

    @mcp.tool()
    def read_process(name: str) -> dict:
        """Return the full source code of a process definition file.

        Parameters
        ----------
        name:
            Stem of the process file (without ``.py``), e.g. ``"clean"`` or
            ``"react"``.  Use ``list_processes`` to discover available names.
        """
        if not holder.is_loaded():
            return {"error": _NO_PROJECT}
        try:
            source = _protocol(holder).read_process(name)
            return {"name": name, "source": source}
        except (FileNotFoundError, ValueError) as exc:
            return {"error": str(exc)}

    # ── Components ────────────────────────────────────────────────────────────

    @mcp.tool()
    def get_components() -> dict:
        """Return the full connectivity/associations.json — the device-to-URL
        mapping for the current machine."""
        if not holder.is_loaded():
            return {"error": _NO_PROJECT}
        return _protocol(holder).read_components()

    @mcp.tool()
    def ping_components(timeout: float = 2.0) -> list[dict]:
        """Verify that all device URLs in ``associations.json`` are reachable.

        Each entry reports ``component``, ``url``, ``online``, ``status_code``,
        ``latency_ms``, ``error``, ``reachability``, and ``reachability_supported``.
        ``reachability`` is the device's live status (``"online"``, ``"offline"``,
        or ``"unknown"``) read from its flowchem ``/is-reachable`` endpoint, when
        available. ``reachability_supported`` is ``False`` if that endpoint 404s
        (the device server needs a flowchem update), or ``None`` if it could not
        be determined (e.g. the base URL itself was unreachable).
        """
        if not holder.is_loaded():
            return [{"error": _NO_PROJECT}]
        return _protocol(holder).ping_components(timeout=timeout)

    # ── Logs ──────────────────────────────────────────────────────────────────

    @mcp.tool()
    def list_logs() -> list[dict]:
        """List all execution log files, most recent first."""
        if not holder.is_loaded():
            return [{"error": _NO_PROJECT}]
        return _protocol(holder).list_logs()

    @mcp.tool()
    def read_log(filename: str) -> str:
        """Read the full text content of a specific execution log file from the log
        directory. Use ``list_logs`` first to discover available filenames.

        Parameters
        ----------
        filename:
            The name of the log file (e.g. ``'protocol_executed_20240101T120000.log'``).
        """
        if not holder.is_loaded():
            return _NO_PROJECT
        return _protocol(holder).read_log(filename)

    @mcp.tool()
    def search_logs(query: str, max_results: int = 50) -> list[dict]:
        """Search all active log files for lines containing *query*.

        Case-insensitive. Returns up to *max_results* entries, each with
        ``filename``, ``line_number``, and ``line``.
        """
        if not holder.is_loaded():
            return [{"error": _NO_PROJECT}]
        return _protocol(holder).search_logs(query, max_results=max_results)

    # ── Run control (additional) ──────────────────────────────────────────────

    @mcp.tool()
    def get_active_run() -> dict:
        """Return the active run ID without consuming queued execution events.

        Returns ``null`` for ``active_run_id`` when no run is in progress.
        Unlike ``get_run_status`` this does not drain the event queue.
        """
        return {"active_run_id": holder.active_run_id()}

    @mcp.tool()
    def drain_run_pool() -> list[dict]:
        """Return all pending device commands and delete their pool files.

        Reads every ``*.jsonl`` file under ``log/pool/``, collects every JSON
        line, deletes the files, and returns the full list. Returns an empty
        list when no commands have been issued since the last poll.

        Poll at a comfortable interval (e.g. every 500 ms) while a run is
        active to see live device activity.
        """
        if not holder.is_loaded():
            return [{"error": _NO_PROJECT}]
        if holder.project_dir is None:
            return [{"error": _NO_PROJECT}]
        pool_dir = holder.project_dir / "log" / "pool"
        if not pool_dir.exists():
            return []
        commands: list[dict] = []
        for f in pool_dir.glob("*.jsonl"):
            try:
                for line in f.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line:
                        commands.append(json.loads(line))
                f.unlink()
            except (OSError, json.JSONDecodeError):
                pass
        return commands

    # ── Components (additional) ───────────────────────────────────────────────

    @mcp.tool()
    def ping_component(component: str, timeout: float = 2.0) -> dict:
        """Verify that a single configured device URL is reachable.

        Also reports ``reachability`` (the device's live status from its
        flowchem ``/is-reachable`` endpoint) and ``reachability_supported``
        (``False`` if that endpoint 404s, meaning the device server needs a
        flowchem update).

        Parameters
        ----------
        component:
            Component name as defined in ``connectivity/associations.json``.
        timeout:
            HTTP request timeout in seconds.
        """
        if not holder.is_loaded():
            return {"error": _NO_PROJECT}
        try:
            return _protocol(holder).ping_component(component, timeout)
        except KeyError as exc:
            return {"error": str(exc)}

    # ── Monitoring ────────────────────────────────────────────────────────────

    @mcp.tool()
    def discover_component_commands(
        component: str, timeout: float = 5.0
    ) -> dict | list:
        """List GET commands a component exposes via its live OpenAPI schema.

        Fetches ``{device_url}/openapi.json`` from the running device server.
        Use the returned ``command`` values when registering variables via
        ``set_monitoring_config``.

        Parameters
        ----------
        component:
            Component name as defined in ``connectivity/associations.json``.
        timeout:
            HTTP request timeout in seconds.
        """
        if not holder.is_loaded():
            return {"error": _NO_PROJECT}
        try:
            return _monitoring(holder).discover(component, timeout=timeout)
        except KeyError as exc:
            return {"error": str(exc)}
        except Exception as exc:
            return {
                "error": f"Device server unreachable or has no OpenAPI schema: {exc}"
            }

    @mcp.tool()
    def get_monitoring_config() -> dict:
        """Return the current monitoring registration.

        Returns ``sample_time``, ``request_timeout``, and ``variables`` — the
        list of component/command pairs that will be polled when a session starts.
        """
        if not holder.is_loaded():
            return {"error": _NO_PROJECT}
        return _monitoring(holder).read_config()

    @mcp.tool()
    def set_monitoring_config(
        sample_time: float,
        variables: list[dict],
        request_timeout: float = 5.0,
    ) -> dict:
        """Register which variables to monitor.

        Persisted to ``connectivity/monitoring.json`` so the registration
        survives a server restart. Does not start polling — call
        ``start_monitoring`` to turn monitoring on.

        Parameters
        ----------
        sample_time:
            Seconds between sampling ticks (must be > 0).
        variables:
            List of variable dicts. Each entry requires ``component`` and
            ``command`` keys, and optionally ``kwargs`` (extra query parameters).
            Example: ``[{"component": "reactor", "command": "temperature"}]``
        request_timeout:
            Per-request timeout in seconds. A hung device only delays its own
            reading (must be > 0).
        """
        if not holder.is_loaded():
            return {"error": _NO_PROJECT}
        _monitoring(holder).write_config(
            {
                "sample_time": sample_time,
                "request_timeout": request_timeout,
                "variables": variables,
            }
        )
        return _monitoring(holder).read_config()

    @mcp.tool()
    def get_monitoring_state() -> dict:
        """Return the current monitoring state.

        ``effective_on`` is true whenever readings are being polled, whether
        from the manual toggle (``manual_on``) or because a protocol run has
        forced monitoring on (``run_active``). ``recording``/``run_id`` are
        set only while an active run has opted in to persisting readings to
        disk.
        """
        if not holder.is_loaded():
            return {"error": _NO_PROJECT}
        return _monitoring(holder).get_state()

    @mcp.tool()
    def start_monitoring() -> dict:
        """Turn monitoring on manually using the current registered config.

        Idempotent if already on. Fails if no variables are registered, or
        if a protocol run currently has monitoring forced on — the manual
        toggle isn't available while a run is active.
        """
        if not holder.is_loaded():
            return {"error": _NO_PROJECT}
        try:
            _monitoring(holder).start()
        except (ValueError, MonitoringRunActiveError) as exc:
            return {"error": str(exc)}
        return _monitoring(holder).get_state()

    @mcp.tool()
    def stop_monitoring() -> dict:
        """Turn monitoring off manually. Idempotent if already off.

        Fails if a protocol run currently has monitoring forced on.
        """
        if not holder.is_loaded():
            return {"error": _NO_PROJECT}
        try:
            _monitoring(holder).stop()
        except MonitoringRunActiveError as exc:
            return {"error": str(exc)}
        return _monitoring(holder).get_state()

    @mcp.tool()
    def get_monitoring_latest() -> dict:
        """Return the latest reading per registered variable — the live dashboard feed."""
        if not holder.is_loaded():
            return {"error": _NO_PROJECT}
        return _monitoring(holder).get_latest()

    @mcp.tool()
    def get_monitoring_history(component: str, command: str) -> list[dict]:
        """Return the in-memory reading history for one variable, most recent last.

        Bounded to a fixed number of readings — this is the live
        visualization buffer, not a full recorded profile. Returns ``[]``
        for a variable that hasn't been polled yet.

        Parameters
        ----------
        component:
            Component name as registered in the monitoring config.
        command:
            GET command/path as registered in the monitoring config.
        """
        if not holder.is_loaded():
            return [{"error": _NO_PROJECT}]
        return _monitoring(holder).get_history(component, command)

    @mcp.tool()
    def get_monitoring_profile(
        run_id: str,
        component: str,
        command: str,
        tail: int | None = None,
    ) -> list[dict]:
        """Read back the recorded profile for one variable from a past run.

        Returns every recorded reading (one entry per sampling tick, including
        failed/missed ticks with ``error`` set) in execution order, from
        ``log/monitoring/{run_id}/``. Only populated for runs started with
        ``record_monitoring=True``. Pass ``tail`` to return only the last N
        readings.

        Parameters
        ----------
        run_id:
            Run ID returned by ``start_run``.
        component:
            Component name as registered in the monitoring config.
        command:
            GET command/path as registered in the monitoring config.
        tail:
            If set, return only the last N readings.
        """
        if not holder.is_loaded():
            return [{"error": _NO_PROJECT}]
        try:
            return _monitoring(holder).read_recording(
                run_id, component, command, tail=tail
            )
        except FileNotFoundError as exc:
            return [{"error": str(exc)}]

    # ── Custom routes ────────────────────────────────────────────────────────

    @mcp.tool()
    def discover_custom_routes() -> list[dict]:
        """List the custom routes registered in this project's
        customizations/routers/router_hook.py, with parameter hints
        introspected from each function's signature. Call this before
        call_custom_route to see what's registered and what parameters it
        expects.
        """
        if not holder.is_loaded():
            return [{"error": _NO_PROJECT}]
        return _discover_custom_routes(_project_dir(holder))

    @mcp.tool()
    def call_custom_route(name: str, kwargs: dict | None = None) -> dict:
        """Call a registered custom route by name with keyword arguments.

        Routes are project-defined and may have side effects (e.g. driving
        equipment) — check discover_custom_routes() first. Returns 'ok:
        false' with 'error' set if the registered function itself raises;
        raises are never treated as a failed call.

        Parameters
        ----------
        name:
            Registered route name, from discover_custom_routes().
        kwargs:
            Keyword arguments passed to the registered function.
        """
        if not holder.is_loaded():
            return {"error": _NO_PROJECT}
        try:
            return _call_custom_route(_project_dir(holder), name, kwargs or {})
        except KeyError as exc:
            return {"error": str(exc)}
