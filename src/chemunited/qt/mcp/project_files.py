from __future__ import annotations

from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Any

from chemunited.qt.project.storage import refresh_protocols_registry

FIXED_PROJECT_FILES = {
    "manifest.json",
    "draw/setup.py",
    "connectivity/associations.json",
    "protocols/main_parameters.py",
}
PROTOCOLS_DIR = "protocols"
PROTOCOLS_SKIP = {"__init__", "main_parameters"}


class ProjectFileAccess:
    def __init__(self, working_dir_provider: Callable[[], Path | None]):
        self._working_dir_provider = working_dir_provider

    def list_files(self) -> list[dict[str, Any]]:
        working_dir = self._require_working_dir()
        relative_paths = set(FIXED_PROJECT_FILES)
        protocols_dir = working_dir / PROTOCOLS_DIR
        if protocols_dir.exists():
            for path in protocols_dir.glob("*.py"):
                rel = f"{PROTOCOLS_DIR}/{path.name}"
                if self._is_protocol_file_path(rel):
                    relative_paths.add(rel)

        files = []
        for rel in sorted(relative_paths):
            try:
                path = self._resolve_allowed(rel, must_exist=False)
            except ValueError:
                continue
            entry: dict[str, Any] = {
                "path": rel,
                "exists": path.exists(),
                "kind": "protocol" if self._is_protocol_file_path(rel) else "project",
            }
            if path.exists():
                stat = path.stat()
                entry["size"] = stat.st_size
                entry["modified"] = stat.st_mtime
            files.append(entry)
        return files

    def read_file(self, relative_path: str) -> str:
        path = self._resolve_allowed(relative_path, must_exist=True)
        return path.read_text(encoding="utf-8")

    def write_file(self, relative_path: str, content: str) -> dict[str, Any]:
        path = self._resolve_allowed(relative_path, must_exist=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        rel = self._normalize_relative_path(relative_path)
        if self._is_protocol_file_path(rel):
            refresh_protocols_registry(self._require_working_dir())
        return {"path": rel, "bytes": len(content.encode("utf-8"))}

    def delete_file(self, relative_path: str) -> dict[str, Any]:
        rel = self._normalize_relative_path(relative_path)
        if not self._is_protocol_file_path(rel):
            raise ValueError("Only normal protocols/*.py files can be deleted.")

        path = self._resolve_allowed(rel, must_exist=False)
        deleted = path.exists()
        if deleted:
            path.unlink()
        refresh_protocols_registry(self._require_working_dir())
        return {"path": rel, "deleted": deleted}

    def _require_working_dir(self) -> Path:
        working_dir = self._working_dir_provider()
        if working_dir is None:
            raise RuntimeError("No project is currently open.")
        return Path(working_dir)

    def _resolve_allowed(self, relative_path: str, *, must_exist: bool) -> Path:
        rel = self._normalize_relative_path(relative_path)
        if not self._is_allowed_path(rel):
            raise ValueError(f"Path is not exposed through project MCP: {rel}")

        root = self._require_working_dir().resolve()
        path = root.joinpath(*PurePosixPath(rel).parts)

        parent = path.parent.resolve(strict=path.parent.exists())
        if not parent.is_relative_to(root):
            raise ValueError("Path escapes the current project.")

        if must_exist and not path.exists():
            raise FileNotFoundError(rel)

        if path.exists() and not path.resolve().is_relative_to(root):
            raise ValueError("Path escapes the current project.")
        return path

    def _is_allowed_path(self, relative_path: str) -> bool:
        return relative_path in FIXED_PROJECT_FILES or self._is_protocol_file_path(
            relative_path
        )

    def _is_protocol_file_path(self, relative_path: str) -> bool:
        parts = PurePosixPath(relative_path).parts
        if len(parts) != 2 or parts[0] != PROTOCOLS_DIR:
            return False
        path = PurePosixPath(relative_path)
        return path.suffix == ".py" and path.stem not in PROTOCOLS_SKIP

    @staticmethod
    def _normalize_relative_path(relative_path: str) -> str:
        if not relative_path:
            raise ValueError("Path is required.")
        normalized = PurePosixPath(relative_path.replace("\\", "/"))
        if normalized.is_absolute() or ".." in normalized.parts:
            raise ValueError("Only relative project paths are allowed.")
        if str(normalized) in {"", "."}:
            raise ValueError("Path is required.")
        return normalized.as_posix()
