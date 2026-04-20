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
        self._session.export_chemunited(chemunited_path)

        logger.bind(window=WindowCategory.SETUP).info(
            f"Project added at {self._session.source_file}"
        )
        self._record_recent_project(chemunited_path)

    def open_project(self, path: Path) -> None:
        session = self._open_session(path)
        draw_data = session.load_draw()

        self._reset_project_state()
        self._session = session
        self.working_dir = session.working_dir
        self._restore_draw_data(draw_data)

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
        # TODO: save protocols
        self._session.export_chemunited(export_destination)

        if comment:
            self._session.git_snapshot(comment)

        logger.bind(window=WindowCategory.SETUP).success(
            f"Project saved to {self._session.source_file}"
        )
        if self._session.source_file is not None:
            self._record_recent_project(self._session.source_file)

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
