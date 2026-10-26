"""MonitoringService — a single, project-wide sensor-monitoring poll loop.

Polling uses a throwaway ``Platform`` (a fresh read of
``connectivity/associations.json``, no ``pool_json_log``) rather than reusing
whatever ``Platform`` a live protocol run holds in memory — so monitoring never
pollutes a run's pool log. Every request still takes the device's
process-wide lock (see ``device_locks``), so a monitoring read never reaches a
device at the same moment as a run command; a read that can't get the lock
in time skips that tick. Note: none of the three client protocols currently
has a timeout passthrough (see ``ProtocolService.send_component_command``'s
docstring for the same caveat) — a hung device can stall a poll tick longer
than ``request_timeout`` would suggest.

There is no session concept: monitoring is a single on/off toggle per
project. Every reading is kept in a bounded in-memory buffer (powers the
live dashboard) and, only while a protocol run has opted in via
``on_run_started(run_id, record=True)``, is also appended to
``log/monitoring/{run_id}/{component}__{command}.jsonl`` for that run's
duration (``{component}__{command}__{params}.jsonl`` for a variable with
parameters).

Readings are keyed by ``monitoring_key``: device, command and parameters, so
two variables on one command with different parameters (two ADC channels,
say) keep their own readings.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests
from loguru import logger

from ...clients.base import _pop_thread_resilient_errors
from ...clients.http import ComponentClient, device_not_served
from ...exceptions import DeviceBusyError
from ...monitoring_context import MonitoringContext
from ...platform import Platform
from ..monitoring_store import MonitoringStore

_DEFAULT_CONFIG: dict[str, Any] = {
    "sample_time": 5.0,
    "request_timeout": 5.0,
    "variables": [],
}


def _canonical(value: Any) -> Any:
    # Integral floats as ints: the dashboard writes 2.0 as 2 in its keys too.
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {str(key): _canonical(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    return value


def canonical_kwargs(kwargs: dict[str, Any] | None) -> str:
    """*kwargs* as canonical JSON (sorted keys, no spaces); ``""`` for none."""
    if not kwargs:
        return ""
    return json.dumps(
        _canonical(kwargs), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def monitoring_key(
    component: str, command: str, kwargs: dict[str, Any] | None = None
) -> str:
    """The key of one monitored variable's readings.

    ``component::command`` for a variable without parameters, as before
    parameters were part of the key; ``component::command::{canonical
    JSON}`` otherwise.
    """
    key = f"{component}::{command}"
    params = canonical_kwargs(kwargs)
    return f"{key}::{params}" if params else key


_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._+=,-]")


def _safe_close(client: Any, component_name: str) -> None:
    """Best-effort cleanup for a throwaway client — never masks a poll result."""
    try:
        client.close()
    except Exception as exc:
        logger.warning(
            "Failed to close throwaway client for '{}': {}", component_name, exc
        )


class MonitoringService:
    def __init__(
        self,
        project_dir: Path,
        store: MonitoringStore,
        stop_run: Callable[[str | None], bool] | None = None,
    ) -> None:
        self._project_dir = project_dir
        self._store = store
        # Stops the active protocol run with a reason (``RunStore.cancel``);
        # published to custom sources as ``MonitoringContext.stop_run`` while
        # polling.
        self._stop_run = stop_run

    # ── Discovery ────────────────────────────────────────────────────────────

    def discover(self, component: str, timeout: float = 5.0) -> list[dict[str, Any]]:
        """List readable commands a component exposes.

        Flowchem: via the device server's live OpenAPI schema (depends on the
        external flowchem server actually serving ``{root}/openapi.json``
        — unverified from this repo, since flowchem itself is not vendored
        here). SiLA2/OPC UA: via the client's own ``discover_commands()``,
        filtered to read-only (``get``) entries — parameter shape differs by
        protocol (raw OpenAPI parameter objects for flowchem; ``{name, in,
        required, type}`` dicts for sila2/opcua). ``"custom"`` is a
        pseudo-component: its "commands" are the function names registered
        in the project's ``customizations/monitoring/monitoring_hook.py``.

        Raises ``DeviceCommunicationError`` if a flowchem server serves nothing
        at the component's URL, rather than returning an empty list.
        """
        if component == "custom":
            return [
                {"command": name, "summary": "", "parameters": []}
                for name in self._load_custom_sources()
            ]
        connectivity = self._read_associations()
        platform = Platform.from_project_dir(self._project_dir)
        client = None
        try:
            if component not in platform:
                self._component_url(
                    connectivity, component
                )  # raises KeyError either way
            client = platform[component]

            if isinstance(client, ComponentClient):
                parts = urlsplit(client.base_url)
                root = f"{parts.scheme}://{parts.netloc}"
                prefix = parts.path.rstrip("/") + "/"
                response = requests.get(f"{root}/openapi.json", timeout=timeout)
                response.raise_for_status()
                schema = response.json()
                results = []
                served = False
                for path, methods in schema.get("paths", {}).items():
                    if not path.startswith(prefix) or not isinstance(methods, dict):
                        continue
                    served = True
                    get_op = methods.get("get")
                    if get_op is None:
                        continue
                    results.append(
                        {
                            "command": path[len(prefix) :],
                            "summary": get_op.get("summary", ""),
                            "parameters": get_op.get("parameters", []),
                        }
                    )
                if not served:
                    raise device_not_served(root, prefix)
                return results

            return [
                {
                    "command": meta["name"],
                    "summary": meta.get("summary", ""),
                    "parameters": [
                        {"name": pname, **pdesc}
                        for pname, pdesc in meta.get("parameters", {}).items()
                    ],
                }
                for meta in client.discover_commands(timeout=timeout).values()
                if meta["type"] == "get"
            ]
        finally:
            if client is not None:
                _safe_close(client, component)

    # ── Config (persisted to connectivity/monitoring.json) ─────────────────────

    @property
    def _config_path(self) -> Path:
        return self._project_dir / "connectivity" / "monitoring.json"

    def read_config(self) -> dict[str, Any]:
        if not self._config_path.exists():
            return dict(_DEFAULT_CONFIG)
        return json.loads(self._config_path.read_text(encoding="utf-8"))

    def write_config(self, config: dict[str, Any]) -> None:
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        self._config_path.write_text(
            json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    # ── Manual on/off ────────────────────────────────────────────────────────

    def start(self) -> None:
        """Turn monitoring on manually; this also makes the platform view live.

        Works with no variables registered (the view then goes live with
        nothing to read) and during a run, when it only sets the manual
        flag: polling continues for the run, and stays on after it.
        """
        stop_event = self._store.try_manual_start()
        if stop_event is not None:
            self._spawn_poll_thread(stop_event)

    def stop(self) -> None:
        """Turn monitoring off manually; the platform view stops being live.

        During a run only the manual flag changes: polling continues for the
        run and stops when it ends.
        """
        self._store.try_manual_stop()

    def get_state(self) -> dict[str, Any]:
        return self._store.snapshot()

    def get_latest(self) -> dict[str, Any]:
        return self._store.get_latest()

    def get_history(
        self,
        component: str,
        command: str,
        kwargs: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        return self._store.get_history(monitoring_key(component, command, kwargs))

    # ── Run-lifecycle hooks (called by RunnerService) ───────────────────────

    def on_run_started(self, run_id: str, *, record: bool) -> None:
        """Force monitoring on for the duration of a protocol run.

        Never raises — a monitoring hiccup must never abort a protocol run.
        """
        try:
            if record and not self.read_config().get("variables"):
                logger.warning(
                    "record_monitoring was requested for run '{}' but no "
                    "monitoring variables are configured; nothing will be recorded.",
                    run_id,
                )
            stop_event = self._store.begin_run(run_id, record)
            if stop_event is not None:
                self._spawn_poll_thread(stop_event)
        except Exception:
            logger.exception(
                "monitoring on_run_started hook failed for run '{}'", run_id
            )

    def on_run_finished(self) -> None:
        """Release the run-forced monitoring state. Never raises."""
        try:
            self._store.end_run()
        except Exception:
            logger.exception("monitoring on_run_finished hook failed")

    # ── Recording read-back ──────────────────────────────────────────────────

    def read_recording(
        self,
        run_id: str,
        component: str,
        command: str,
        tail: int | None = None,
        kwargs: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        path = self._run_dir(run_id) / self._variable_filename(
            component, command, kwargs
        )
        if not path.exists():
            raise FileNotFoundError(
                f"No recording for '{component}'/'{command}' in run '{run_id}'."
            )
        lines = path.read_text(encoding="utf-8").splitlines()
        if tail is not None:
            lines = lines[-tail:]
        return [json.loads(line) for line in lines if line.strip()]

    # ── Polling loop ─────────────────────────────────────────────────────────

    def _spawn_poll_thread(self, stop_event: threading.Event) -> None:
        thread = threading.Thread(
            target=self._poll_loop,
            args=(stop_event,),
            daemon=True,
        )
        thread.start()

    def _poll_loop(self, stop_event: threading.Event) -> None:
        config = self.read_config()
        sample_time = float(config["sample_time"])
        variables: list[dict[str, Any]] = config["variables"]

        # One throwaway Platform for the whole ON-cycle (not per tick) — reconnecting
        # a gRPC/OPC UA session every `sample_time` seconds would be wasteful. Variables
        # are grouped by component so each component's one shared client is only ever
        # touched by one pool worker at a time: sharing it across per-variable workers
        # in the same tick would trip ComponentClient's non-blocking per-device lock
        # (ConcurrentClientAccessError) the same way two protocol-run nodes hitting one
        # device would.
        platform = Platform.from_project_dir(self._project_dir, error_resilient=True)
        # Published for CUSTOM_SOURCES functions to read a real device through
        # (see MonitoringContext) — same Platform/locks as everything else this
        # ON-cycle, so a custom source's device read can't double-connect to a
        # device another pool worker is mid-fetching in the same tick.
        MonitoringContext.platform = platform
        # Published alongside it, so a custom source acting as a safety
        # interlock can stop the active run (MonitoringContext.stop_run).
        MonitoringContext._stop_run = self._stop_run
        # Reloaded fresh each ON-cycle, same lifetime as `platform` above — editing
        # monitoring_hook.py takes effect the next time monitoring is (re)started,
        # no server restart needed.
        custom_sources = self._load_custom_sources()
        groups: dict[str, list[dict[str, Any]]] = {}
        for var in variables:
            groups.setdefault(self._group_key(var), []).append(var)

        tick = 0
        try:
            with ThreadPoolExecutor(
                max_workers=max(1, len(groups)), thread_name_prefix="monitoring"
            ) as pool:
                while not stop_event.is_set():
                    tick_start = time.monotonic()

                    # Re-derived every tick: a single ON-cycle (this thread) can span
                    # multiple recording windows — manual-on, then a run starts and
                    # recording begins under one run_id, then the run ends but the
                    # loop keeps going because manual_on was already true, then a
                    # later run starts recording again under a different run_id.
                    recording, run_id = self._store.poll_context()
                    run_dir = self._run_dir(run_id) if recording and run_id else None

                    futures = {
                        pool.submit(
                            self._fetch_group, platform, custom_sources, group_vars
                        )
                        for group_vars in groups.values()
                    }
                    for future in futures:
                        for var, reading in future.result():
                            if reading.get("skipped"):
                                continue
                            reading["tick"] = tick
                            key = monitoring_key(
                                var["component"], var["command"], var.get("kwargs")
                            )
                            self._store.record_reading(key, reading)
                            if run_dir is not None:
                                self._write_reading(run_dir, var, reading)
                    tick += 1
                    remaining = sample_time - (time.monotonic() - tick_start)
                    if remaining > 0:
                        stop_event.wait(timeout=remaining)
        finally:
            # Cleared before closing clients so nothing reading MonitoringContext
            # from outside this ON-cycle can observe a half-torn-down Platform.
            # Only if still this cycle's: monitoring turned off and straight back
            # on (one run ending as the next starts) has a new cycle publish
            # before this one finishes its last tick.
            if MonitoringContext.platform is platform:
                MonitoringContext.platform = None
                MonitoringContext._stop_run = None
            for component, client in platform.items():
                _safe_close(client, component)

    @staticmethod
    def _group_key(var: dict[str, Any]) -> str:
        """Poll-tick group for one variable.

        Real components group by component name, so variables sharing one
        physical device share its one client (see _poll_loop's docstring).
        Custom sources have no physical client to share, but must still
        never be forced into the same group as a *different* custom source
        — grouping by `command` (the registered function name) gives each
        distinct custom source its own pool worker while letting repeat
        entries of the *same* custom source share one, symmetric with real
        components.
        """
        if var["component"] == "custom":
            return f"custom::{var['command']}"
        return var["component"]

    def _load_custom_sources(self) -> dict[str, Any]:
        """Load CUSTOM_SOURCES from the project's monitoring hook file, if any.

        Never raises: a missing file yields an empty registry silently (custom
        sources are optional); a file that fails to import or doesn't export a
        CUSTOM_SOURCES dict is logged and also yields an empty registry — a
        broken hook must never abort a poll cycle, matching the "a monitoring
        hiccup must never abort a protocol run" principle used throughout
        this service.
        """
        path = (
            self._project_dir / "customizations" / "monitoring" / "monitoring_hook.py"
        )
        if not path.exists():
            return {}
        try:
            spec = importlib.util.spec_from_file_location("monitoring_hook", path)
            if spec is None or spec.loader is None:
                raise ImportError(f"Cannot create a module spec from {path}")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)  # type: ignore[union-attr]
            sources = getattr(module, "CUSTOM_SOURCES", None)
            if not isinstance(sources, dict):
                raise AttributeError(
                    "monitoring_hook.py does not export a CUSTOM_SOURCES dict"
                )
            return sources
        except Exception:
            logger.exception("Failed to load custom monitoring sources from {}", path)
            return {}

    def _fetch_group(
        self,
        platform: Platform,
        custom_sources: dict[str, Any],
        group_vars: list[dict[str, Any]],
    ) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        """Fetch every variable in one poll-tick group sequentially — see
        _group_key for why the group's variables must share one worker.
        """
        return [
            (
                var,
                self._fetch_one(
                    platform,
                    var["component"],
                    var["command"],
                    var.get("kwargs", {}),
                    custom_sources,
                ),
            )
            for var in group_vars
        ]

    def _fetch_one(
        self,
        platform: Platform,
        component: str,
        command: str,
        kwargs: dict[str, Any],
        custom_sources: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = datetime.now().isoformat()
        if component == "custom":
            func = (custom_sources or {}).get(command)
            if func is None:
                return {
                    "time": now,
                    "value": None,
                    "error": f"Custom source '{command}' is not registered.",
                }
            try:
                return {"time": now, "value": func(**kwargs), "error": None}
            except Exception as exc:
                return {"time": now, "value": None, "error": str(exc)}
        if component not in platform:
            return {
                "time": now,
                "value": None,
                "error": f"Component '{component}' has no configured connection for its protocol.",
            }
        client = platform[component]
        is_http = isinstance(client, ComponentClient)
        _pop_thread_resilient_errors()  # discard stale entries from thread-pool reuse
        try:
            raw = client.get(command, params=kwargs or None, raw_response=is_http)
        except DeviceBusyError:
            # Another request to this device was in flight for too long: skip
            # this tick and keep the last reading (see device_locks).
            return {"time": now, "value": None, "error": None, "skipped": True}
        except Exception as exc:
            return {"time": now, "value": None, "error": str(exc)}
        if is_http:
            value = self._parse_value(raw)
        else:
            value = raw
        errors = _pop_thread_resilient_errors()
        if errors:
            return {"time": now, "value": None, "error": str(errors[-1])}
        return {"time": now, "value": value, "error": None}

    @staticmethod
    def _parse_value(response: requests.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return response.text.strip()

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _run_dir(self, run_id: str) -> Path:
        return self._project_dir / "log" / "monitoring" / run_id

    @staticmethod
    def _variable_filename(
        component: str, command: str, kwargs: dict[str, Any] | None = None
    ) -> str:
        safe_command = command.strip("/").replace("/", "__")
        if not kwargs:
            return f"{component}__{safe_command}.jsonl"
        # Readable where possible ("channel=2"), with a short hash whenever
        # making the name file-safe lost something, so names never collide.
        readable = ",".join(
            f"{key}={value}" for key, value in sorted(_canonical(kwargs).items())
        )
        params = _UNSAFE_FILENAME_CHARS.sub("-", readable)[:60]
        if params != readable:
            digest = hashlib.sha256(canonical_kwargs(kwargs).encode()).hexdigest()
            params = f"{params}-{digest[:8]}"
        return f"{component}__{safe_command}__{params}.jsonl"

    def _write_reading(
        self, run_dir: Path, var: dict[str, Any], reading: dict[str, Any]
    ) -> None:
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / self._variable_filename(
            var["component"], var["command"], var.get("kwargs")
        )
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(reading) + "\n")

    def _read_associations(self) -> dict[str, Any]:
        path = self._project_dir / "connectivity" / "associations.json"
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _component_url(connectivity: dict[str, Any], component: str) -> str:
        for assoc in connectivity["associations"]:
            if assoc["component"] == component:
                component_url = assoc.get("component_url", "").strip()
                if not component_url:
                    raise KeyError(
                        f"Component '{component}' has no component_url configured."
                    )
                return component_url
        raise KeyError(f"Component '{component}' not found in associations.")
