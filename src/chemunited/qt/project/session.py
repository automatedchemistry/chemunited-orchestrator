from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .git_manager import GitManager
from .manifest import ProjectManifest
from .storage import (
    delete_process,
    duplicate_process,
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
    from chemunited.qt.protocols.workflows import ProcessWorkflow


class ProjectSession:

    def __init__(self) -> None:
        self.working_dir: Path | None = None
        self.source_file: Path | None = None
        self.manifest: ProjectManifest | None = None
        self.git: GitManager | None = None

    def _require_working_dir(self) -> Path:
        if self.working_dir is None:
            raise RuntimeError("No project is currently open.")
        return self.working_dir

    def _require_manifest(self) -> ProjectManifest:
        if self.manifest is None:
            raise RuntimeError("Project manifest is not loaded.")
        return self.manifest

    # ── Lifecycle (unchanged) ──────────────────────────────────────────────────

    def new(
        self, name: str, location: Path, description: str = "", init_git: bool = True
    ) -> None:
        self.working_dir = location / name
        self.working_dir.mkdir(parents=True, exist_ok=True)
        self.manifest = ProjectManifest(
            name=name,
            chemunited_version="0.1.0",
            description=description,
        )
        self.manifest.save(self.working_dir)
        if init_git:
            self.git = GitManager.init(self.working_dir)

    def open_directory(self, working_dir: Path) -> None:
        self.working_dir = working_dir
        self.manifest = ProjectManifest.load(working_dir)
        self.git = GitManager.open(working_dir)

    def import_chemunited(
        self, chemunited_file: Path, location: Path | None = None, overwrite: bool = False
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
                    "Cannot import archive into an existing non-project path: "
                    f"{target}"
                )

        has_existing_git = (target / ".git").is_dir()
        unpack(chemunited_file, target)
        self.working_dir = target
        self.source_file = chemunited_file
        self.manifest = ProjectManifest.load(target)
        if has_existing_git:
            self.git = GitManager.open(target)
        else:
            self.git = GitManager.init_from_import(target, chemunited_file.name)

    def export_chemunited(self, destination: Path | None = None) -> Path:
        working_dir = self._require_working_dir()
        manifest = self._require_manifest()
        dest = destination or working_dir.parent / manifest.name
        manifest.save(working_dir)
        pack(working_dir, dest)
        self.source_file = dest.with_suffix(".chemunited")
        return self.source_file

    # ── Draw (unchanged) ───────────────────────────────────────────────────────

    def save_draw(self, draw_data: dict) -> None:
        save_draw(self._require_working_dir(), draw_data)
        if self.git:
            self.git.commit_draw()

    def load_draw(self) -> dict:
        return load_draw(self._require_working_dir())

    # ── Protocols ──────────────────────────────────────────────────────────────

    def save_process(self, process_name: str, content: str) -> None:
        save_process(self._require_working_dir(), process_name, content)
        if self.git:
            self.git.commit_process(process_name)

    def sync_process(self, process_name: str, workflow: ProcessWorkflow) -> bool:
        synced = sync_process(self._require_working_dir(), process_name, workflow)
        if synced and self.git:
            self.git.commit_process(process_name)
        return synced

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
        if self.git:
            self.git.commit_process(process_name, deleted=True)

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
        if self.git:
            self.git.commit_process(new_name, created=True)

    def list_processes(self) -> list[str]:
        return list_processes(self._require_working_dir())

    def load_process_classes(self) -> dict:
        return load_process_classes(self._require_working_dir())

    # ── Parameters ─────────────────────────────────────────────────────────────

    def save_main_parameters(self, content: str) -> None:
        save_main_parameters(self._require_working_dir(), content)
        if self.git:
            self.git.commit_main_parameters()

    def load_main_parameters(self) -> str:
        return load_main_parameters(self._require_working_dir())

    # ── Connectivity (unchanged) ───────────────────────────────────────────────

    def save_connectivity(self, data: dict) -> None:
        save_connectivity(self._require_working_dir(), data)

    def load_connectivity(self) -> dict:
        return load_connectivity(self._require_working_dir())

    # ── Git ────────────────────────────────────────────────────────────────────

    def git_snapshot(self, message: str) -> bool:
        return self.git.snapshot(message) if self.git else False

    def git_status(self) -> dict | None:
        return self.git.status() if self.git else None

    def git_log(self) -> list[dict]:
        return self.git.log() if self.git else []
