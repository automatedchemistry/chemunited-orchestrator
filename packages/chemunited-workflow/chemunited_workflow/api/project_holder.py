"""ProjectHolder — manages the optional active project and its services."""

from __future__ import annotations

import json
import threading
from pathlib import Path

from chemunited_workflow.command_events import CommandObserver
from chemunited_workflow.project_loader import ProjectModules

from .device_state import DeviceStateStore, PictureDeriver
from .monitoring_store import MonitoringStore
from .run_store import RunStore
from .services.monitoring import MonitoringService, monitoring_key
from .services.protocol import ProtocolService
from .services.runner import RunnerService


def _associated_components(project_dir: Path) -> list[str]:
    """Component names in ``connectivity/associations.json`` (none if unreadable)."""
    path = project_dir / "connectivity" / "associations.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [str(assoc["component"]) for assoc in data.get("associations", [])]
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return []


def _display_bindings(project_dir: Path) -> dict[str, str]:
    """Each LCD's name -> the monitoring key it shows, from the desktop export."""
    path = project_dir / "draw" / "platform-live.json"
    try:
        displays = json.loads(path.read_text(encoding="utf-8")).get("displays", {})
        return {
            str(name): monitoring_key(
                display["component"], display["command"], display.get("kwargs")
            )
            for name, display in displays.items()
        }
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {}


def _monitored_keys(monitoring: MonitoringService) -> set[str]:
    try:
        variables = monitoring.read_config().get("variables", [])
        return {
            monitoring_key(var["component"], var["command"], var.get("kwargs"))
            for var in variables
        }
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return set()


def _picture_deriver(project_dir: Path) -> PictureDeriver | None:
    # Imported here, the way clients/__init__.py defers the SiLA2 and OPC UA
    # clients: command_tracker is the one module that uses chemunited-core.
    from .command_tracker import load_command_tracker

    return load_command_tracker(project_dir)


class ProjectHolder:
    """Thread-safe holder for the currently active project's service instances.

    The ``RunStore`` and ``MonitoringStore`` are created once at construction and
    persist across project switches so that in-flight run/session history is not
    lost.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._run_store = RunStore()
        self._monitoring_store = MonitoringStore()
        self._project_dir: Path | None = None
        self._protocol_service: ProtocolService | None = None
        self._runner_service: RunnerService | None = None
        self._monitoring_service: MonitoringService | None = None
        self._device_state: DeviceStateStore | None = None

    # ── Read accessors ────────────────────────────────────────────────────────

    @property
    def project_dir(self) -> Path | None:
        with self._lock:
            return self._project_dir

    @property
    def protocol_service(self) -> ProtocolService | None:
        with self._lock:
            return self._protocol_service

    @property
    def runner_service(self) -> RunnerService | None:
        with self._lock:
            return self._runner_service

    @property
    def monitoring_service(self) -> MonitoringService | None:
        with self._lock:
            return self._monitoring_service

    @property
    def device_state(self) -> DeviceStateStore | None:
        """The live state of the loaded project's devices (see ``device_state``)."""
        with self._lock:
            return self._device_state

    @property
    def run_store(self) -> RunStore:
        return self._run_store

    @property
    def monitoring_store(self) -> MonitoringStore:
        return self._monitoring_store

    def command_observer(self, run_id: str | None = None) -> CommandObserver | None:
        """The observer that puts device commands on the live platform view."""
        store = self.device_state
        return None if store is None else store.observer(run_id)

    def is_loaded(self) -> bool:
        with self._lock:
            return self._project_dir is not None

    def active_run_id(self) -> str | None:
        return self._run_store.active_run_id

    def active_protocol(self) -> str | None:
        """Filename of the protocol the active run was started from, if any."""
        if self.active_run_id() is None:
            return None
        rec = self._run_store.get()
        return rec.protocol_filename if rec is not None else None

    # ── Mutation ──────────────────────────────────────────────────────────────

    def load(self, modules: ProjectModules) -> None:
        """Replace the active project.

        Builds fresh ``ProtocolService`` and ``RunnerService`` instances (reusing
        the same ``RunStore``) and a fresh device state store, in which every
        device starts unknown, then swaps them under the lock.
        """
        new_monitoring = MonitoringService(
            project_dir=modules.project_dir,
            store=self._monitoring_store,
            stop_run=self._run_store.cancel,
        )
        new_device_state = DeviceStateStore(
            _associated_components(modules.project_dir),
            deriver=_picture_deriver(modules.project_dir),
            displays=_display_bindings(modules.project_dir),
            monitored_keys=lambda: _monitored_keys(new_monitoring),
        )
        new_protocol = ProtocolService(
            project_dir=modules.project_dir,
            processes=modules.processes,
            configs=modules.configs,
            main_parameter_class=modules.main_parameter_class,
            device_state=new_device_state,
        )
        new_runner = RunnerService(
            project_dir=modules.project_dir,
            processes=modules.processes,
            configs=modules.configs,
            run_store=self._run_store,
            monitoring_service=new_monitoring,
            device_state=new_device_state,
        )
        self._run_store.set_project_dir(modules.project_dir)
        self._monitoring_store.set_reading_listener(new_device_state.record_reading)
        with self._lock:
            self._project_dir = modules.project_dir
            self._protocol_service = new_protocol
            self._runner_service = new_runner
            self._monitoring_service = new_monitoring
            self._device_state = new_device_state
