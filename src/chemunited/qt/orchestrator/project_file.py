from pathlib import Path

from loguru import logger
from PyQt5.QtWidgets import QFileDialog

from chemunited.qt.project.manifest import ProjectManifest
from chemunited.qt.project.session import ProjectSession
from chemunited.qt.shared.enums import WindowCategory

from .execution import OrchestratorExecution


class OrchestratorProjectFile(OrchestratorExecution):

    def __init__(self, parent):
        super().__init__(parent)
        self.working_dir: Path | None = None
        self._session: ProjectSession | None = None

    def load(self):
        pass

    def save(self, comment: str = "") -> None:
        if not self.working_dir:
            path, _ = QFileDialog.getSaveFileName(
                self.parent_ref,
                "Save Project",
                str(Path.home()),
                "ChemUnited Project (*.chemunited)",
            )
            if not path:
                return
            chemunited_path = Path(path)
            if not chemunited_path.suffix:
                chemunited_path = chemunited_path.with_suffix(".chemunited")
            self.working_dir = chemunited_path.parent / chemunited_path.stem

        if self._session is None:
            self._session = ProjectSession()
            if ProjectManifest.exists(self.working_dir):
                self._session.open_directory(self.working_dir)
            else:
                self._session.new(
                    name=self.working_dir.name,
                    location=self.working_dir.parent,
                )

        self._session.save_draw(self._build_draw_data())
        self._session.export_chemunited()

        if comment:
            self._session.git_snapshot(comment)

        logger.bind(window=WindowCategory.SETUP).info(
            f"Project saved to {self._session.source_file}"
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
