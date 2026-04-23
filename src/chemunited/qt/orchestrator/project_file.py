from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from loguru import logger
from PyQt5.QtWidgets import QFileDialog, QMessageBox
from PyQt5.QtCore import pyqtSlot

from chemunited.qt.project.manifest import ProjectManifest
from chemunited.qt.project.platform_svg import (
    PLATFORM_SVG_RELATIVE_PATH,
    export_platform_svg,
)
from chemunited.qt.project.recent import RecentProjectsStore
from chemunited.qt.project.session import ProjectSession
from chemunited.qt.project.writer import render_python_script
from chemunited.qt.protocols.workflows import ProcessWorkflow
from chemunited.qt.shared.enums import WindowCategory
from chemunited.qt.shared.enums.protocols_enum import ProtocolBlock

from .draw import call_component_model
from .execution import OrchestratorExecution
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


class OrchestratorProjectFile(OrchestratorExecution):

    def __init__(self, parent):
        super().__init__(parent)
        self.working_dir: Path | None = None
        self._session: ProjectSession | None = None
        self.recent_projects = RecentProjectsStore()
        self.recent_projects.prune_missing()

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

        self.open_project(Path(path))

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
        self._session.save_main_parameters(self._render_main_parameters_script(self.working_dir))
        self._session.export_chemunited(chemunited_path)

        logger.bind(window=WindowCategory.SETUP).info(
            f"Project added at {self._session.source_file}"
        )
        self._record_recent_project(chemunited_path)

    def open_project(self, path: Path) -> None:
        try:
            session = self._open_session(path)
            draw_data = session.load_draw()
            process_classes = session.load_process_classes()
        except Exception as exc:
            logger.bind(window=WindowCategory.SETUP).opt(exception=exc).error(
                f"Could not open project '{path.name}': {exc}"
            )
            return

        self._reset_project_state()
        self._session = session
        self.working_dir = session.working_dir
        self._restore_draw_data(draw_data)
        self._restore_protocols(process_classes)

        logger.bind(window=WindowCategory.SETUP).success(f"Project loaded from {path}")
        self._record_recent_project(path)

    def open_recent_project(self, path: Path) -> None:
        if not self._confirm_replace_current_project():
            return

        if not path.exists():
            self.recent_projects.remove(path)
            logger.bind(window=WindowCategory.SETUP).warning(
                f"Recent project no longer exists: {path}"
            )
            return

        self.open_project(path)

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
        self._session.save_main_parameters(self._render_main_parameters_script(self.working_dir))
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

    def _open_session(self, path: Path) -> ProjectSession:
        session = ProjectSession()
        if path.is_dir():
            session.open_directory(path)
        elif path.suffix.lower() == ".chemunited":
            session.import_chemunited(path)
        elif path.name == "manifest.json":
            session.open_directory(path.parent)
        else:
            raise ValueError(f"Unsupported project path: {path}")
        return session

    def _reset_project_state(self) -> None:
        for name in list(self.connections.keys()):
            if name in self.connections:
                self.remove_connection(name)

        for name in list(self.components.keys()):
            if name in self.components:
                self.remove_component(name)

        self.parent_ref.scene_attribute.clearSelection()
        self.clear_protocols()

    def _restore_draw_data(self, draw_data: dict) -> None:
        for component in draw_data.get("components", []):
            try:
                self.add_component(**self._validated_component_payload(dict(component)))
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

    def _validated_component_payload(self, payload: dict) -> dict:
        payload.pop("type", None)
        figure = payload.get("figure")
        if not isinstance(figure, str):
            raise ValueError("Project component is missing a valid figure.")

        try:
            mode_class = call_component_model(figure)
        except AttributeError:
            return payload
        return dict(mode_class.model_validate(payload))

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
        from chemunited.qt.protocols.workflows.workflow_rules import (
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
                if pos is not None and block is not None:
                    block.position = tuple(pos)
                continue

            workflow.add_block(
                node_id=node_id,
                method=attrs.get("method") or node_id,
                position=attrs.get("position", (0.0, 0.0)),
                label=attrs.get("label"),
                description=attrs.get("description"),
                block_tag=_infer_block_tag(node_id, attrs, graph),
                ports_numbers=_coerce_ports_numbers(attrs.get("ports_numbers", 1)),
            )

        for source, target, attrs in graph.edges(data=True):
            loopback = attrs.get("loopback", False)
            condition = attrs.get("condition")
            trigger_on = attrs.get("trigger_on", False)
            source_block = workflow.get_block(source)
            source_tag = source_block.block_tag if source_block else ProtocolBlock.SCRIPT
            start_role = resolve_render_start_role(
                source_tag,
                start_role=None,
                loopback=loopback,
                trigger_on=trigger_on,
                condition=condition,
            )
            workflow.add_connection(
                source, target,
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
        existing: dict[str, dict] = {}
        server_url = ""
        if self._session is not None:
            raw = self._session.load_connectivity()
            server_url = raw.get("server_url", "")
            for assoc in raw.get("associations", []):
                existing[assoc["component"]] = assoc
        associations = [
            existing.get(name, {"component": name, "device_name": "", "device_url": ""})
            for name in self.components
        ]
        return {"server_url": server_url, "associations": associations}

    def _build_draw_data(self) -> dict:
        components = [
            component.graph.base_mode_instance.model_dump(mode="json")
            for component in self.components.values()
        ]
        connections = [
            conn.base_mode_instance.model_dump(mode="json")
            for conn in self.connections.values()
        ]
        return {"components": components, "connections": connections}
