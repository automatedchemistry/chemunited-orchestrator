from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from chemunited_core.compounds import COMPOUNDS, ChemicalEntity
from loguru import logger
from PyQt5.QtCore import QThread, QTimer, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import QFileDialog, QInputDialog, QMessageBox

from chemunited.project.manifest import ProjectManifest
from chemunited.project.platform_svg import (
    PLATFORM_DEVICES_RELATIVE_PATH,
    PLATFORM_SVG_RELATIVE_PATH,
    export_platform_svg,
)
from chemunited.project.recent import RecentProjectsStore
from chemunited.project.session import ProjectSession
from chemunited.project.storage import ensure_protocols_historic_dir
from chemunited.project.writer import render_python_script
from chemunited.protocols.workflows import ProcessWorkflow
from chemunited.shared.enums import WindowCategory
from chemunited.shared.enums.protocols_enum import ProtocolBlock

from .draw import call_component_model
from .execution import OrchestratorExecution
from .inventory_state import (
    apply_inventory_status_payload,
    build_inventory_status_payload,
)
from .protocols import is_valid_name


def _coerce_block_tag(value: object) -> ProtocolBlock | None:
    if isinstance(value, ProtocolBlock):
        return value
    if isinstance(value, str):
        try:
            return ProtocolBlock(value)
        except ValueError:
            return None
    return None


def _infer_block_tag(node_id: str, attrs: dict, graph) -> ProtocolBlock:
    saved_block_tag = _coerce_block_tag(attrs.get("block_tag"))
    if saved_block_tag is not None:
        return saved_block_tag

    outgoing_edges = list(graph.out_edges(node_id, data=True))
    if any(edge_attrs.get("loopback") is True for _, _, edge_attrs in outgoing_edges):
        return ProtocolBlock.LOOP
    if any(edge_attrs.get("condition") is False for _, _, edge_attrs in outgoing_edges):
        return ProtocolBlock.IF

    candidate_names = [node_id]
    method_name = attrs.get("method")
    if isinstance(method_name, str):
        candidate_names.append(method_name)

    lowered_candidates = [candidate.lower() for candidate in candidate_names]
    if any(
        candidate == "loop" or candidate.startswith("loop_")
        for candidate in lowered_candidates
    ):
        return ProtocolBlock.LOOP
    if any(
        candidate in {"if", "conditional"}
        or candidate.startswith("if_")
        or candidate.startswith("conditional_")
        for candidate in lowered_candidates
    ):
        return ProtocolBlock.IF
    return ProtocolBlock.SCRIPT


def _coerce_ports_numbers(value: object) -> int:
    if not isinstance(value, (int, float, str)):
        return 1
    try:
        ports_numbers = int(value)
    except (TypeError, ValueError):
        return 1
    return max(1, ports_numbers)


def _coerce_inflection_points(value: object) -> list[tuple[float, float]]:
    if not isinstance(value, (list, tuple)):
        return []

    points: list[tuple[float, float]] = []
    for point in value:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            continue
        try:
            x = float(point[0])
            y = float(point[1])
        except (TypeError, ValueError):
            continue
        points.append((x, y))
    return points


def _quantity_magnitude(value, unit: str) -> float:
    return float(value.to(unit).magnitude)


@dataclass
class ProjectLoadPayload:
    session: ProjectSession
    draw_data: dict
    process_classes: dict
    connectivity_data: dict


class ProjectLoadThread(QThread):
    loaded = pyqtSignal(object)
    failed = pyqtSignal(object)

    def __init__(
        self,
        path: Path,
        *,
        overwrite: bool = False,
        source_file: Path | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.path = path
        self.overwrite = overwrite
        self.source_file = source_file

    def run(self) -> None:
        try:
            payload = _load_project_payload(
                self.path,
                overwrite=self.overwrite,
                source_file=self.source_file,
            )
        except Exception as exc:
            self.failed.emit(exc)
            return
        self.loaded.emit(payload)


def _open_project_session(path: Path, overwrite: bool = False) -> ProjectSession:
    session = ProjectSession()
    if path.is_dir():
        session.open_directory(path)
    elif path.suffix.lower() == ".chemunited":
        session.import_chemunited(path, overwrite=overwrite)
    elif path.name == "manifest.json":
        session.open_directory(path.parent)
    else:
        raise ValueError(f"Unsupported project path: {path}")
    return session


def _load_project_payload(
    path: Path,
    *,
    overwrite: bool = False,
    source_file: Path | None = None,
) -> ProjectLoadPayload:
    session = _open_project_session(path, overwrite=overwrite)
    if source_file is not None:
        session.source_file = source_file
    return ProjectLoadPayload(
        session=session,
        draw_data=session.load_draw(),
        process_classes=session.load_process_classes(),
        connectivity_data=session.load_connectivity(),
    )


class OrchestratorProjectFile(OrchestratorExecution):
    def __init__(self, parent):
        super().__init__(parent)
        self.working_dir: Path | None = None
        self._session: ProjectSession | None = None
        self.recent_projects = RecentProjectsStore()
        self.recent_projects.prune_missing()
        self._project_load_thread: ProjectLoadThread | None = None

    @property
    def is_project_operation_running(self) -> bool:
        return self._project_load_thread is not None

    def load(self) -> None:
        if not self._confirm_replace_current_project():
            return

        path, _ = QFileDialog.getOpenFileName(
            self.parent_ref,
            "Load Project",
            str(Path.home()),
            "ChemUnited Project (*.chemunited);;Project Manifest (manifest.json)",
        )
        if not path:
            return

        self.open_project_async(Path(path))

    def new_project(self) -> None:
        if not self._confirm_replace_current_project():
            return

        chemunited_path = self._select_project_file("Add Project")
        if chemunited_path is None:
            return

        self._reset_project_state()
        self.working_dir = chemunited_path.parent / chemunited_path.stem
        self._session = ProjectSession()
        self._session.new(name=self.working_dir.name, location=self.working_dir.parent)
        self._save_platform_svg()
        self._session.save_draw(self._build_draw_data())
        self._ensure_main_parameters_script()
        self._session.export_chemunited(chemunited_path)

        logger.bind(window=WindowCategory.SETUP).info(
            f"Project added at {self._session.source_file}"
        )
        self._record_recent_project(chemunited_path)

    def open_project(self, path: Path, overwrite: bool = False) -> None:
        """Open a project file or manifest-backed project directory.

        The project session is loaded from ``path`` and used to restore the
        drawing canvas, connectivity graph, protocol classes, working
        directory, and current session reference. Any error raised while the
        session is being opened or its required project data is being read is
        logged for the setup window and leaves the current project unchanged.

        Args:
            path: Path to a ``.chemunited`` export or project manifest.
            overwrite: Whether an extracted project directory may replace an
                existing directory when importing an archive.
        """
        try:
            payload = _load_project_payload(path, overwrite=overwrite)
        except Exception as exc:
            logger.bind(window=WindowCategory.SETUP).opt(exception=exc).error(
                f"Could not open project '{path.name}': {exc}"
            )
            return

        self._apply_loaded_project(payload)

        logger.bind(window=WindowCategory.SETUP).success(f"Project loaded from {path}")
        self._record_recent_project(path)

    def open_project_async(self, path: Path, overwrite: bool = False) -> bool:
        if self.is_project_operation_running:
            logger.bind(window=WindowCategory.SETUP).warning(
                "A project operation is already running."
            )
            return False

        self._show_busy_status("Loading project", f"Opening {path.name}...")
        return self._start_project_load_thread(
            path,
            overwrite=overwrite,
            success_message=f"Project loaded from {path}",
            done_message="Project loaded",
            failure_prefix=f"Could not open project '{path.name}'",
            recent_project=path,
        )

    def refresh_project(self) -> bool:
        """Confirm and schedule a project refresh from disk."""
        if self.refresh_project_block_reason() is not None:
            return False
        if not self._confirm_refresh_project():
            return False
        return self.refresh_current_project_async()

    def refresh_project_block_reason(self) -> str | None:
        if self.working_dir is None:
            return "Load or create a project before refreshing."
        if self._has_online_project_monitor():
            return "Disconnect the running project API before refreshing."
        return None

    def refresh_current_project(self) -> bool:
        """Reload the currently open project from its working directory."""
        if self.working_dir is None:
            logger.bind(window=WindowCategory.SETUP).warning(
                "No project loaded — cannot refresh."
            )
            return False

        working_dir = self.working_dir
        source_file = self._session.source_file if self._session is not None else None
        try:
            payload = _load_project_payload(working_dir, source_file=source_file)
        except Exception as exc:
            logger.bind(window=WindowCategory.SETUP).opt(exception=exc).error(
                f"Could not refresh project '{working_dir.name}': {exc}"
            )
            return False

        self._apply_loaded_project(payload)

        logger.bind(window=WindowCategory.SETUP).success(
            f"Project refreshed from {working_dir}"
        )
        return True

    def refresh_current_project_async(self) -> bool:
        if self.working_dir is None:
            logger.bind(window=WindowCategory.SETUP).warning(
                "No project loaded - cannot refresh."
            )
            return False
        if self.is_project_operation_running:
            logger.bind(window=WindowCategory.SETUP).warning(
                "A project operation is already running."
            )
            return False

        working_dir = self.working_dir
        source_file = self._session.source_file if self._session is not None else None
        self._show_busy_status("Refreshing project", f"Reloading {working_dir.name}...")
        return self._start_project_load_thread(
            working_dir,
            source_file=source_file,
            success_message=f"Project refreshed from {working_dir}",
            done_message="Project refreshed",
            failure_prefix=f"Could not refresh project '{working_dir.name}'",
            after_success=self._sync_project_views_after_refresh,
        )

    def _run_refresh_current_project(self) -> None:
        if self.refresh_current_project():
            QTimer.singleShot(0, self._sync_project_views_after_refresh)
        update_project_actions = getattr(
            self.parent_ref, "update_project_actions", None
        )
        if callable(update_project_actions):
            update_project_actions()

    def open_recent_project(self, path: Path) -> None:
        if not self._confirm_replace_current_project():
            return

        if not path.exists():
            self.recent_projects.remove(path)
            logger.bind(window=WindowCategory.SETUP).warning(
                f"Recent project no longer exists: {path}"
            )
            return

        self.open_project_async(path)

    def save(self, comment: str = "") -> None:
        export_destination: Path | None = None

        if not self.working_dir:
            chemunited_path = self._select_project_file(
                "Save Project",
                confirm_overwrite=False,
            )
            if chemunited_path is None:
                return
            self.working_dir = chemunited_path.parent / chemunited_path.stem
            export_destination = chemunited_path

        if self._session is None:
            self._session = ProjectSession()
            if ProjectManifest.exists(self.working_dir):
                self._session.open_directory(self.working_dir)
            else:
                self._session.new(
                    name=self.working_dir.name,
                    location=self.working_dir.parent,
                )

        export_destination = export_destination or self._session.source_file
        self._save_platform_svg()
        self._session.save_draw(self._build_draw_data())
        self._save_protocols()
        self._ensure_main_parameters_script()
        self._session.save_connectivity(self._build_connectivity_data())
        self._session.export_chemunited(export_destination)

        if comment:
            self._session.git_snapshot(comment)

        logger.bind(window=WindowCategory.SETUP).success(
            f"Project saved to {self._session.source_file}"
        )
        if self._session.source_file is not None:
            self._record_recent_project(self._session.source_file)

    @pyqtSlot(str, str)
    def rename_process(self, old_name: str, new_name: str) -> None:
        # override OrchestratorProtocols.rename_process
        if not is_valid_name(new_name):
            self._warn_user(
                f"Invalid name {new_name!r}. Only letters, numbers, _ and - are allowed."
            )
            return
        if old_name not in self.protocols:
            logger.error(f"Process not found: {old_name!r}")
            return
        if new_name in self.protocols:
            self._warn_user(f"A process named {new_name!r} already exists.")
            return

        if self._session is None or self.working_dir is None:
            super().rename_process(old_name, new_name)
            self.save()
            return

        saved_processes = set(self._session.list_processes())
        if old_name not in saved_processes:
            super().rename_process(old_name, new_name)
            self.save()
            return

        if self._persist_renamed_process_file(old_name, new_name):
            super().rename_process(old_name, new_name)

    @pyqtSlot(str)
    def remove_process(self, name: str) -> None:
        # override OrchestratorProtocols.remove_process
        if name not in self.protocols:
            logger.error(f"Process not found: {name!r}")
            return
        if self._persist_removed_process_file(name):
            super().remove_process(name)

    def _select_project_file(
        self,
        title: str,
        *,
        confirm_overwrite: bool = True,
    ) -> Path | None:
        options = QFileDialog.Options()
        if not confirm_overwrite:
            options |= QFileDialog.DontConfirmOverwrite

        path, _ = QFileDialog.getSaveFileName(
            self.parent_ref,
            title,
            str(Path.home()),
            "ChemUnited Project (*.chemunited)",
            options=options,
        )
        if not path:
            return None
        return self._normalize_project_file(Path(path))

    def _normalize_project_file(self, path: Path) -> Path:
        if path.suffix.lower() != ".chemunited":
            return path.with_suffix(".chemunited")
        return path

    def _persist_renamed_process_file(self, old_name: str, new_name: str) -> bool:
        try:
            if self._session is None:
                return False
            self._session.rename_process(old_name, new_name)
        except Exception as exc:
            logger.bind(window=WindowCategory.SETUP).opt(exception=exc).warning(
                "Could not rename saved process file "
                f"{old_name!r} -> {new_name!r}: {exc}"
            )
            self._warn_user(
                "The process was not renamed in the editor, and the saved project "
                "file could not be updated."
            )
            return False
        return True

    def _persist_removed_process_file(self, name: str) -> bool:
        if self._session is None or self.working_dir is None:
            return True

        saved_processes = set(self._session.list_processes())
        if name not in saved_processes:
            return True

        try:
            self._session.delete_process(name)
        except Exception as exc:
            logger.bind(window=WindowCategory.SETUP).opt(exception=exc).warning(
                f"Could not delete saved process file {name!r}: {exc}"
            )
            self._warn_user(
                "The process was not removed in the editor because the saved "
                "project file could not be deleted."
            )
            return False
        return True

    def _save_platform_svg(self) -> None:
        if self.working_dir is None:
            return
        export_platform_svg(
            self.parent_ref.scene_attribute,
            self.working_dir / PLATFORM_SVG_RELATIVE_PATH,
            devices_path=self.working_dir / PLATFORM_DEVICES_RELATIVE_PATH,
            components=self.components.items(),
        )

    def _record_recent_project(self, path: Path | None) -> None:
        if path is None:
            return
        self.recent_projects.add(path)

    def _confirm_replace_current_project(self) -> bool:
        if not self.components and not self.connections and not self.protocols:
            return True

        reply = QMessageBox.question(
            self.parent_ref,
            "Replace current project?",
            "The current canvas will be cleared before the project is changed.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return reply == QMessageBox.Yes

    def _confirm_refresh_project(self) -> bool:
        reply = QMessageBox.question(
            self.parent_ref,
            "Refresh project?",
            "Reload the project from disk? "
            "Unsaved changes in the app will be discarded.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return reply == QMessageBox.Yes

    def _has_online_project_monitor(self) -> bool:
        working_dir = self.working_dir
        if working_dir is None:
            return False

        for monitor in self._project_monitor_windows():
            monitor_orchestrator = getattr(monitor, "orchestrator", None)
            monitor_working_dir = getattr(monitor_orchestrator, "working_dir", None)
            if not self._same_path(working_dir, monitor_working_dir):
                continue

            status_widget = getattr(monitor, "status_widget", None)
            status_text = getattr(status_widget, "text", None)
            if callable(status_text):
                if status_text() == "Online":
                    return True
                continue
            if getattr(monitor, "api_process", None) is not None:
                return True

        return False

    def _project_monitor_windows(self) -> list[Any]:
        pre_run_frame = getattr(self.parent_ref, "preRunFrame", None)
        protocols_list = getattr(pre_run_frame, "protocols_list_widget", None)
        return list(getattr(protocols_list, "_monitor_windows", []))

    @staticmethod
    def _same_path(left: Path | None, right: object) -> bool:
        if left is None or right is None:
            return False
        if not isinstance(right, (str, Path)):
            return False
        try:
            right_path = Path(right)
        except TypeError:
            return False
        return left.resolve() == right_path.resolve()

    def _sync_project_views_after_refresh(self) -> None:
        protocols_widget = getattr(self.parent_ref, "protocols_widget", None)
        if protocols_widget is not None:
            protocols_widget.sync_list()

        command_list = getattr(self.parent_ref, "command_list", None)
        if command_list is not None:
            command_list.sync_protocols()

        pre_run_frame = getattr(self.parent_ref, "preRunFrame", None)
        if pre_run_frame is not None:
            pre_run_frame.sync()

    def _start_project_load_thread(
        self,
        path: Path,
        *,
        overwrite: bool = False,
        source_file: Path | None = None,
        success_message: str,
        done_message: str,
        failure_prefix: str,
        recent_project: Path | None = None,
        after_success: Callable[[], None] | None = None,
    ) -> bool:
        thread = ProjectLoadThread(
            path,
            overwrite=overwrite,
            source_file=source_file,
            parent=self,
        )
        self._project_load_thread = thread
        thread.loaded.connect(
            lambda payload: self._on_project_load_success(
                payload,
                success_message=success_message,
                done_message=done_message,
                recent_project=recent_project,
                after_success=after_success,
            )
        )
        thread.failed.connect(
            lambda exc: self._on_project_load_failed(
                exc,
                failure_prefix=failure_prefix,
            )
        )
        thread.finished.connect(thread.deleteLater)
        self._notify_project_actions_changed()
        thread.start()
        return True

    def _on_project_load_success(
        self,
        payload: ProjectLoadPayload,
        *,
        success_message: str,
        done_message: str,
        recent_project: Path | None,
        after_success: Callable[[], None] | None,
    ) -> None:
        try:
            self._apply_loaded_project(payload)
            logger.bind(window=WindowCategory.SETUP).success(success_message)
            self._record_recent_project(recent_project)
            if after_success is not None:
                after_success()
            self._finish_busy_status(done_message)
        finally:
            self._project_load_thread = None
            self._notify_project_actions_changed()

    def _on_project_load_failed(self, exc: Exception, *, failure_prefix: str) -> None:
        logger.bind(window=WindowCategory.SETUP).opt(exception=exc).error(
            f"{failure_prefix}: {exc}"
        )
        self._fail_busy_status(f"{failure_prefix}: {exc}")
        self._project_load_thread = None
        self._notify_project_actions_changed()

    def _apply_loaded_project(self, payload: ProjectLoadPayload) -> None:
        self._reset_project_state()
        self._session = payload.session
        self.working_dir = payload.session.working_dir
        self._restore_draw_data(payload.draw_data)
        self._restore_connectivity_data(payload.connectivity_data)
        self._restore_protocols(payload.process_classes)

    def _show_busy_status(self, title: str, message: str) -> None:
        show_busy_status = getattr(self.parent_ref, "show_busy_status", None)
        if callable(show_busy_status):
            show_busy_status(title, message)

    def _finish_busy_status(self, message: str) -> None:
        finish_busy_status = getattr(self.parent_ref, "finish_busy_status", None)
        if callable(finish_busy_status):
            finish_busy_status(message)

    def _fail_busy_status(self, message: str) -> None:
        fail_busy_status = getattr(self.parent_ref, "fail_busy_status", None)
        if callable(fail_busy_status):
            fail_busy_status(message)

    def _notify_project_actions_changed(self) -> None:
        update_project_actions = getattr(
            self.parent_ref,
            "update_project_actions",
            None,
        )
        if callable(update_project_actions):
            update_project_actions()

    def _open_session(self, path: Path, overwrite: bool = False) -> ProjectSession:
        return _open_project_session(path, overwrite=overwrite)

    def _reset_project_state(self) -> None:
        close_main_parameters_editor = getattr(
            self.parent_ref,
            "close_main_parameters_editor",
            None,
        )
        if callable(close_main_parameters_editor):
            close_main_parameters_editor()

        if hasattr(self.parent_ref, "drawGraph"):
            # Only needed for setup window
            cleanup_draw_state = getattr(self.parent_ref.drawGraph, "_cleanup", None)
            if callable(cleanup_draw_state):
                cleanup_draw_state()

        for component in self.components.values():
            if component._widget is not None:
                component._widget.close()

        scene = self.parent_ref.scene_attribute
        scene.clearSelection()
        scene.clear()
        scene.update()

        self.connections.clear()
        self.components.clear()
        self.clear_protocols()
        COMPOUNDS.clear()
        self._sync_compound_list()

    def _restore_draw_data(self, draw_data: dict) -> None:
        for compound in draw_data.get("compounds", []):
            try:
                COMPOUNDS.register(ChemicalEntity(**dict(compound)))
            except Exception as exc:
                name = dict(compound).get("name", "unknown")
                logger.bind(window=WindowCategory.SETUP).opt(exception=exc).warning(
                    f"Skipped compound '{name}': {exc}"
                )

        for component in draw_data.get("components", []):
            try:
                payload = self._validated_component_payload(dict(component))
                self.add_component(**payload)
            except Exception as exc:
                name = dict(component).get("name", "unknown")
                logger.bind(window=WindowCategory.SETUP).opt(exception=exc).warning(
                    f"Skipped component '{name}': {exc}"
                )

        for connection in draw_data.get("connections", []):
            try:
                self._restore_connection(dict(connection))
            except Exception as exc:
                logger.bind(window=WindowCategory.SETUP).opt(exception=exc).warning(
                    f"Skipped connection: {exc}"
                )

        apply_inventory_status_payload(self.components, draw_data.get("inventory", {}))  # type: ignore[arg-type]
        for comp in self.components.values():
            comp.graph.sync_visuals()
        self._sync_compound_list()

    def _restore_connectivity_data(self, connectivity_data: dict) -> None:
        server_url = connectivity_data.get("server_url", "").rstrip("/")
        for association in connectivity_data.get("associations", []):
            component_name = association.get("component", "")
            component_url = (
                association.get(
                    "component_url",
                    association.get("device_url", ""),
                )
                or ""
            ).lstrip("/")
            if component_name not in self.components:
                continue

            component = self.components[component_name]
            if not component.inf.is_electronic:
                continue
            if server_url and component_url:
                self._apply_component_connectivity(
                    component_name,
                    f"{server_url}/{component_url}",
                )

    def _validated_component_payload(self, payload: dict) -> dict:
        payload.pop("type", None)
        payload.pop("inventory", None)
        figure = payload.get("figure")
        if not isinstance(figure, str):
            raise ValueError("Project component is missing a valid figure.")

        try:
            mode_class = call_component_model(figure)
        except AttributeError:
            return payload
        validated = dict(mode_class.model_validate(payload))
        return validated

    def _restore_connection(self, payload: dict) -> None:
        destination = payload.pop("destination", payload.pop("destiny", None))
        if destination is None:
            raise ValueError("Project connection is missing a destination.")

        self.add_connection(
            origin=payload.pop("origin"),
            destiny=destination,
            origin_port=payload.pop("origin_port", 2),
            destiny_port=payload.pop(
                "destination_port",
                payload.pop("destiny_port", 1),
            ),
            **payload,
        )

    def _restore_protocols(self, process_classes: dict) -> None:
        manifest_order = (
            self._session.manifest.processes_order
            if self._session and self._session.manifest
            else []
        )
        names = manifest_order + [n for n in process_classes if n not in manifest_order]

        for name in names:
            cls = process_classes.get(name)
            if cls is None:
                continue
            try:
                workflow = self._workflow_from_process_class(name, cls)
            except Exception as exc:
                logger.bind(window=WindowCategory.SETUP).opt(exception=exc).warning(
                    f"Could not restore protocol {name!r}: {exc}"
                )
                continue
            self.protocols[name] = workflow
            self.parent_ref.workflows_protocol.add_process(name, workflow)

        self.parent_ref.protocols_widget.sync_list()

    @staticmethod
    def _workflow_from_process_class(name: str, cls) -> ProcessWorkflow:
        from chemunited.protocols.workflows.workflow_rules import (
            default_terminal_block_specs,
            resolve_render_start_role,
        )

        config_cls = cls.__orig_bases__[0].__args__[0]
        graph = cls(config=config_cls()).build_workflow()
        workflow = ProcessWorkflow(name)
        terminal_names = {spec.name for spec in default_terminal_block_specs()}

        for node_id, attrs in graph.nodes(data=True):
            if node_id in terminal_names:
                pos = attrs.get("position")
                block = workflow.get_block(node_id)
                if block is not None:
                    if pos is not None:
                        block.position = tuple(pos)
                    block.label = str(attrs.get("label") or node_id)
                    block.description = str(attrs.get("description") or "")
                continue

            workflow.add_block(
                node_id=node_id,
                method=attrs.get("method") or node_id,
                position=attrs.get("position", (0.0, 0.0)),
                label=str(attrs.get("label") or node_id),
                description=str(attrs.get("description") or ""),
                block_tag=_infer_block_tag(node_id, attrs, graph),
                ports_numbers=_coerce_ports_numbers(attrs.get("ports_numbers", 1)),
            )

        for source, target, attrs in graph.edges(data=True):
            loopback = attrs.get("loopback", False)
            condition = attrs.get("condition")
            trigger_on = attrs.get("trigger_on", False)
            source_block = workflow.get_block(source)
            source_tag = (
                source_block.block_tag if source_block else ProtocolBlock.SCRIPT
            )
            start_role = resolve_render_start_role(
                source_tag,
                start_role=None,
                loopback=loopback,
                trigger_on=trigger_on,
                condition=condition,
            )
            workflow.add_connection(
                source,
                target,
                start_role=start_role,
                condition=condition,
                loopback=loopback,
                trigger_on=trigger_on,
                label=attrs.get("label", ""),
                inflection_points=_coerce_inflection_points(
                    attrs.get("inflection_points")
                ),
                max_iterations=attrs.get("max_iterations"),
            )

        return workflow

    def _save_protocols(self) -> None:
        if self._session is None or self.working_dir is None:
            return
        for name, workflow in self.protocols.items():
            synced = self._session.sync_process(name, workflow)
            if synced:
                continue
            logger.bind(window=WindowCategory.SETUP).warning(
                f"Could not sync saved process file for {name!r}."
            )
            self._warn_user(
                "A saved process file could not be updated safely. "
                f"The existing file for {name!r} was left unchanged."
            )
        if self._session.manifest is not None:
            self._session.manifest.processes_order = list(self.protocols.keys())

    def _ensure_main_parameters_script(self) -> None:
        if self._session is None or self.working_dir is None:
            return

        path = self.working_dir / "protocols" / "main_parameters.py"
        if path.exists():
            return

        self._session.save_main_parameters(
            self._render_main_parameters_script(self.working_dir)
        )

    @staticmethod
    def _render_main_parameters_script(working_dir: Path) -> str:
        return render_python_script(
            script="parameter",
            overwrite={
                "---DATA---": datetime.now(timezone.utc).isoformat(),
                "---PROJECT_NAME---": working_dir.name,
            },
        )

    def _build_connectivity_data(self) -> dict:
        server_url = ""
        associations: list[dict] = []
        if self._session is not None:
            # Inspect all electronic component
            for component in self.components.values():
                if not component.inf.is_electronic:
                    continue

                component_url = component.url_component
                if component_url:
                    server_url = component.connectivity.base_url.rstrip("/")
                associations.append(
                    {
                        "component": component.name,
                        "component_url": component_url,
                    }
                )
        return {"server_url": server_url, "associations": associations}

    def _build_draw_data(self) -> dict:
        compounds = [
            self._compound_payload(entity)
            for entity in COMPOUNDS.entities
            if entity.name not in {"air"}
        ]
        components = [
            self._component_payload(component) for component in self.components.values()
        ]
        connections = [
            conn.base_mode_instance.model_dump(mode="json")
            for conn in self.connections.values()
        ]
        inventory = build_inventory_status_payload(self.components.values())
        return {
            "compounds": compounds,
            "components": components,
            "connections": connections,
            "inventory": inventory,
        }

    def _sync_compound_list(self) -> None:
        compound_list = getattr(self.parent_ref, "compound_list", None)
        sync = getattr(compound_list, "sync", None)
        if callable(sync):
            sync()

    @staticmethod
    def _compound_payload(entity: ChemicalEntity) -> dict:
        return {
            "name": entity.name,
            "molecular_weight": _quantity_magnitude(
                entity.molecular_weight,
                "g/mol",
            ),
            "cp_liquid": _quantity_magnitude(entity.cp_liquid, "J/(mol*K)"),
            "cp_gas": _quantity_magnitude(entity.cp_gas, "J/(mol*K)"),
            "density_liquid": _quantity_magnitude(
                entity.density_liquid,
                "kg/m^3",
            ),
            "color_red": entity.color_red,
            "color_green": entity.color_green,
            "color_blue": entity.color_blue,
            "color_alpha": entity.color_alpha,
        }

    @staticmethod
    def _component_payload(component) -> dict:
        return component.graph.base_mode_instance.model_dump(mode="json")

    def save_protocols_historic(self) -> None:
        if self.working_dir is None:
            self._warn_user("Load or create a project before saving protocol scripts.")
            return

        folder = ensure_protocols_historic_dir(self.working_dir)
        data: dict[str, dict[str, Any]] = {}
        pre_run_list = self.parent_ref.preRunFrame.processes_list_widget

        # Main parameters
        if main_parameters := pre_run_list._main_parameters_instance:
            data["main_parameter"] = main_parameters.model_dump(mode="json")

        # Process parameters
        for index, (active_name, process_name) in enumerate(
            pre_run_list.active_processes_in_order()
        ):
            instance = pre_run_list._process_parameter_instances.get(active_name)
            if instance is None:
                path = self.working_dir / "protocols" / f"{process_name}.py"
                model_class = pre_run_list._load_process_parameter_model(
                    path,
                    process_name,
                )
                if model_class is None:
                    return
                instance = pre_run_list._default_instance(model_class, path)
                if instance is None:
                    return
            key = f"{process_name}_{index}"
            data[key] = instance.model_dump(mode="json")

        if not data:  # Should not happen if pre_run_list._active_data is not empty
            return

        # Save as <name>_<timestamp>.json, for example:
        # name_2026-03-27T16-18-00.json
        name, ok = QInputDialog.getText(
            self.parent_ref,
            "Save Protocol Script",
            "Protocol script name:",
        )
        if not ok:
            return

        filename_base = self._protocols_historic_filename_base(name)
        if not filename_base:
            self._warn_user(
                "Protocol script name must contain at least one letter, number, _ or -."
            )
            return

        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
        path = self._next_protocols_historic_path(folder, filename_base, timestamp)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

        self.parent_ref.preRunFrame.protocols_list_widget.fill_cards()
        logger.bind(window=WindowCategory.SETUP).success(
            f"Protocol script saved to {path}"
        )

    @staticmethod
    def _protocols_historic_filename_base(name: str) -> str:
        base = re.sub(r"[^A-Za-z0-9_-]+", "_", name.strip())
        return base.strip("_-")

    @staticmethod
    def _next_protocols_historic_path(
        folder: Path,
        filename_base: str,
        timestamp: str,
    ) -> Path:
        path = folder / f"{filename_base}_{timestamp}.json"
        if not path.exists():
            return path

        suffix = 1
        while True:
            candidate = folder / f"{filename_base}_{timestamp}_{suffix}.json"
            if not candidate.exists():
                return candidate
            suffix += 1
