from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from loguru import logger
from PyQt5.QtWidgets import QFileDialog, QMessageBox

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

from .draw import call_component_model
from .execution import OrchestratorExecution


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
        session = self._open_session(path)
        draw_data = session.load_draw()
        process_classes = session.load_process_classes()

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

    def rename_process(self, old_name: str, new_name: str) -> None:
        if old_name in self.protocols or new_name not in self.protocols:
            return
        if self._persist_renamed_process_file(old_name, new_name):
            super().rename_process(old_name, new_name)

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
        if self._session is None or self.working_dir is None:
            self.save()
            return True

        saved_processes = set(self._session.list_processes())
        if old_name not in saved_processes:
            self.save()
            return True

        try:
            self._session.rename_process(old_name, new_name)
        except Exception as exc:
            logger.bind(window=WindowCategory.SETUP).warning(
                "Could not rename saved process file "
                f"{old_name!r} -> {new_name!r}: {exc}"
            )
            self._warn_user(
                "The process was not renamed in the editor, and the saved project "
                "file could not be updated."
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
            self.add_component(**self._validated_component_payload(dict(component)))

        for connection in draw_data.get("connections", []):
            self._restore_connection(dict(connection))

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
                logger.bind(window=WindowCategory.SETUP).warning(
                    f"Could not restore protocol {name!r}: {exc}"
                )
                continue
            self.protocols[name] = workflow
            self.parent_ref.workflows_protocol.add_process(name, workflow)

        self.parent_ref.protocols_widget.sync_list()

    @staticmethod
    def _workflow_from_process_class(name: str, cls) -> ProcessWorkflow:
        from chemunited.qt.shared.enums.protocols_enum import ProtocolBlock
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
                block_tag=ProtocolBlock.SCRIPT,
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
                max_iterations=attrs.get("max_iterations"),
            )

        return workflow

    def _save_protocols(self) -> None:
        if self._session is None or self.working_dir is None:
            return
        existing_processes = set(self._session.list_processes())
        for name, workflow in self.protocols.items():
            # Project save may scaffold a new process file, but it should not
            # overwrite an existing implementation module.
            if name in existing_processes:
                continue
            self._session.save_process(
                name,
                self._render_new_process_script(name, workflow, self.working_dir),
            )
            existing_processes.add(name)
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

    def _render_new_process_script(self, name: str, workflow: ProcessWorkflow, working_dir: Path) -> str:
        class_name = name.replace("_", " ").title().replace(" ", "") + "Process"
        template = render_python_script(
            script="process",
            overwrite={
                "---DATE---": datetime.now(timezone.utc).isoformat(),
                "---PROJECT_NAME---": working_dir.name,
                "---PROCESS_NAME---": name,
                "---CLASS_NAME---": class_name,
                "---PROCESS_LABEL---": name,
                "---PROCESS_DESCRIPTION---": "",
            },
        )
        workflow_def = self._render_workflow_definition(workflow)
        return template.replace("        ---WORKFLOW_DEFINITION---", workflow_def)

    @staticmethod
    def _render_workflow_definition(workflow: ProcessWorkflow) -> str:
        indent = "        "
        sections = (
            [block.to_script(indent) for _, block in workflow.iter_blocks()]
            + [conn.to_script(start, end, indent) for start, end, conn in workflow.iter_connections()]
        )
        return "\n\n".join(sections) if sections else f"{indent}pass"

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
