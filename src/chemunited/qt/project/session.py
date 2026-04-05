from __future__ import annotations

from pathlib import Path

from .manifest import ProjectManifest
from .storage import (
    pack, unpack,
    save_draw, load_draw,
    save_process, load_process, delete_process,
    rename_process, duplicate_process, list_processes,
    load_process_classes,
    save_main_parameters, load_main_parameters,
    save_connectivity, load_connectivity,
)
from .git_manager import GitManager


class ProjectSession:

    def __init__(self):
        self.working_dir: Path | None = None
        self.source_file: Path | None = None
        self.manifest: ProjectManifest | None = None
        self.git: GitManager | None = None

    # ── Lifecycle (unchanged) ──────────────────────────────────────────────────

    def new(self, name: str, location: Path,
            description: str = "", init_git: bool = True) -> None:
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

    def import_chemunited(self, chemunited_file: Path,
                          location: Path | None = None) -> None:
        name = chemunited_file.stem
        target = (location or chemunited_file.parent) / name
        unpack(chemunited_file, target)
        self.working_dir = target
        self.source_file = chemunited_file
        self.manifest = ProjectManifest.load(target)
        self.git = GitManager.init_from_import(target, chemunited_file.name)

    def export_chemunited(self, destination: Path | None = None) -> Path:
        dest = destination or self.working_dir.parent / self.manifest.name
        self.manifest.save(self.working_dir)
        pack(self.working_dir, dest)
        self.source_file = dest.with_suffix(".chemunited")
        return self.source_file

    # ── Draw (unchanged) ───────────────────────────────────────────────────────

    def save_draw(self, draw_data: dict) -> None:
        save_draw(self.working_dir, draw_data)
        if self.git:
            self.git.commit_draw()

    def load_draw(self) -> dict:
        return load_draw(self.working_dir)

    # ── Protocols ──────────────────────────────────────────────────────────────

    def save_process(self, process_name: str, content: str) -> None:
        save_process(self.working_dir, process_name, content)
        if self.git:
            self.git.commit_process(process_name)

    def load_process(self, process_name: str) -> str:
        return load_process(self.working_dir, process_name)

    def delete_process(self, process_name: str) -> None:
        delete_process(self.working_dir, process_name)
        self.manifest.processes_order = [
            p for p in self.manifest.processes_order
            if p != process_name
        ]
        self.manifest.save(self.working_dir)
        if self.git:
            self.git.commit_process(process_name, deleted=True)

    def rename_process(self, old_name: str, new_name: str) -> None:
        rename_process(self.working_dir, old_name, new_name)
        self.manifest.processes_order = [
            new_name if p == old_name else p
            for p in self.manifest.processes_order
        ]
        self.manifest.save(self.working_dir)

    def duplicate_process(self, source_name: str, new_name: str) -> None:
        duplicate_process(self.working_dir, source_name, new_name)
        self.manifest.processes_order.append(new_name)
        self.manifest.save(self.working_dir)
        if self.git:
            self.git.commit_process(new_name, created=True)

    def list_processes(self) -> list[str]:
        return list_processes(self.working_dir)

    def load_process_classes(self) -> dict:
        return load_process_classes(self.working_dir)

    # ── Parameters ─────────────────────────────────────────────────────────────

    def save_main_parameters(self, content: str) -> None:
        save_main_parameters(self.working_dir, content)
        if self.git:
            self.git.commit_main_parameters()

    def load_main_parameters(self) -> str:
        return load_main_parameters(self.working_dir)

    # ── Connectivity (unchanged) ───────────────────────────────────────────────

    def save_connectivity(self, data: dict) -> None:
        save_connectivity(self.working_dir, data)

    def load_connectivity(self) -> dict:
        return load_connectivity(self.working_dir)

    # ── Git ────────────────────────────────────────────────────────────────────

    def git_snapshot(self, message: str) -> bool:
        return self.git.snapshot(message) if self.git else False

    def git_status(self) -> dict | None:
        return self.git.status() if self.git else None

    def git_log(self) -> list[dict]:
        return self.git.log() if self.git else []