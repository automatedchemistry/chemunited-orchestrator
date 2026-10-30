from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .gitignore import ensure_gitignore
from .manifest import ProjectManifest
from .storage import (
    delete_process,
    duplicate_process,
    ensure_log_dir,
    ensure_protocols_historic_dir,
    list_processes,
    load_connectivity,
    load_draw,
    load_main_parameters,
    load_process,
    load_process_classes,
    pack,
    rename_process,
    save_connectivity,
    save_draw,
    save_main_parameters,
    save_process,
    sync_process,
    unpack,
)

if TYPE_CHECKING:
    from chemunited.protocols.workflows import ProcessWorkflow


class ProjectSession:
    """An open project folder.

    Versioning is up to the user: a project folder can be (or sit inside) a
    git repository, which ChemUnited never writes to. The work-server records
    the repository's commit in each run's manifest.
    """

    def __init__(self) -> None:
        self.working_dir: Path | None = None
        self.source_file: Path | None = None
        self.manifest: ProjectManifest | None = None

    def _require_working_dir(self) -> Path:
        if self.working_dir is None:
            raise RuntimeError("No project is currently open.")
        return self.working_dir

    def _require_manifest(self) -> ProjectManifest:
        if self.manifest is None:
            raise RuntimeError("Project manifest is not loaded.")
        return self.manifest

    # ── Lifecycle (unchanged) ──────────────────────────────────────────────────

    def new(self, name: str, location: Path, description: str = "") -> None:
        self.working_dir = location / name
        self.working_dir.mkdir(parents=True, exist_ok=True)
        ensure_protocols_historic_dir(self.working_dir)
        ensure_log_dir(self.working_dir)
        ensure_gitignore(self.working_dir)
        self.manifest = ProjectManifest(
            name=name,
            chemunited_version="0.1.0",
            description=description,
        )
        self.manifest.save(self.working_dir)

    def open_directory(self, working_dir: Path) -> None:
        self.working_dir = working_dir
        self.manifest = ProjectManifest.load(working_dir)
        ensure_protocols_historic_dir(working_dir)
        ensure_log_dir(working_dir)
        ensure_gitignore(working_dir)

    def import_chemunited(
        self,
        chemunited_file: Path,
        location: Path | None = None,
        overwrite: bool = False,
    ) -> None:
        name = chemunited_file.stem
        target = (location or chemunited_file.parent) / name

        if ProjectManifest.exists(target) and not overwrite:
            self.open_directory(target)
            self.source_file = chemunited_file
            return

        if target.exists():
            if not target.is_dir():
                raise FileExistsError(
                    "Cannot import archive: path exists and is not a directory: "
                    f"{target}"
                )
            if any(target.iterdir()) and not ProjectManifest.exists(target):
                raise FileExistsError(
                    f"Cannot import archive into an existing non-project path: {target}"
                )

        unpack(chemunited_file, target)
        ensure_protocols_historic_dir(target)
        ensure_log_dir(target)
        ensure_gitignore(target)
        self.working_dir = target
        self.source_file = chemunited_file
        self.manifest = ProjectManifest.load(target)

    def export_chemunited(self, destination: Path | None = None) -> Path:
        working_dir = self._require_working_dir()
        manifest = self._require_manifest()
        dest = destination or working_dir.parent / manifest.name
        ensure_protocols_historic_dir(working_dir)
        ensure_log_dir(working_dir)
        ensure_gitignore(working_dir)
        manifest.save(working_dir)
        pack(working_dir, dest)
        self.source_file = dest.with_suffix(".chemunited")
        return self.source_file

    # ── Draw (unchanged) ───────────────────────────────────────────────────────

    def save_draw(self, draw_data: dict) -> None:
        save_draw(self._require_working_dir(), draw_data)

    def load_draw(self) -> dict:
        return load_draw(self._require_working_dir())

    # ── Protocols ──────────────────────────────────────────────────────────────

    def save_process(self, process_name: str, content: str) -> None:
        save_process(self._require_working_dir(), process_name, content)

    def sync_process(self, process_name: str, workflow: ProcessWorkflow) -> bool:
        return sync_process(self._require_working_dir(), process_name, workflow)

    def load_process(self, process_name: str) -> str:
        return load_process(self._require_working_dir(), process_name)

    def delete_process(self, process_name: str) -> None:
        working_dir = self._require_working_dir()
        manifest = self._require_manifest()
        delete_process(working_dir, process_name)
        manifest.processes_order = [
            p for p in manifest.processes_order if p != process_name
        ]
        manifest.save(working_dir)

    def rename_process(self, old_name: str, new_name: str) -> None:
        working_dir = self._require_working_dir()
        manifest = self._require_manifest()
        rename_process(working_dir, old_name, new_name)
        manifest.processes_order = [
            new_name if p == old_name else p for p in manifest.processes_order
        ]
        manifest.save(working_dir)

    def duplicate_process(self, source_name: str, new_name: str) -> None:
        working_dir = self._require_working_dir()
        manifest = self._require_manifest()
        duplicate_process(working_dir, source_name, new_name)
        manifest.processes_order.append(new_name)
        manifest.save(working_dir)

    def list_processes(self) -> list[str]:
        return list_processes(self._require_working_dir())

    def load_process_classes(self) -> dict:
        return load_process_classes(self._require_working_dir())

    # ── Parameters ─────────────────────────────────────────────────────────────

    def save_main_parameters(self, content: str) -> None:
        save_main_parameters(self._require_working_dir(), content)

    def load_main_parameters(self) -> str:
        return load_main_parameters(self._require_working_dir())

    # ── Connectivity (unchanged) ───────────────────────────────────────────────

    def save_connectivity(self, data: dict) -> None:
        save_connectivity(self._require_working_dir(), data)

    def load_connectivity(self) -> dict:
        return load_connectivity(self._require_working_dir())
