from __future__ import annotations

import json
from pathlib import Path
from typing import TypeAlias

from platformdirs import user_data_dir


APP_NAME = "ChemUnited Orchestrator"
APP_AUTHOR = "ChemUnited"
RECENT_PROJECTS_FILENAME = "recent_projects.json"
MAX_RECENT_PROJECTS = 10
PathList: TypeAlias = list[Path]
StringList: TypeAlias = list[str]


def default_recent_projects_path() -> Path:
    return Path(user_data_dir(APP_NAME, APP_AUTHOR)) / RECENT_PROJECTS_FILENAME


class RecentProjectsStore:
    def __init__(self, path: Path | None = None, limit: int = MAX_RECENT_PROJECTS):
        self.path = path or default_recent_projects_path()
        self.limit = limit

    def list(self) -> PathList:
        return [Path(path) for path in self._read_paths()]

    def prune_missing(self) -> PathList:
        paths = self._read_paths()
        existing_paths: PathList = []
        serialized_paths: StringList = []
        seen_paths: set[Path] = set()

        for path in paths:
            normalized = self._normalize(Path(path))
            if normalized in seen_paths or not self._exists(normalized):
                continue

            seen_paths.add(normalized)
            existing_paths.append(normalized)
            serialized_paths.append(str(normalized))

        serialized_paths = serialized_paths[: self.limit]
        if serialized_paths != paths:
            self._write_paths(serialized_paths)

        return existing_paths[: self.limit]

    def add(self, project_path: Path) -> None:
        normalized = self._normalize(project_path)
        paths = [
            path
            for path in self._read_paths()
            if self._normalize(Path(path)) != normalized
        ]
        paths.insert(0, str(normalized))
        self._write_paths(paths[: self.limit])

    def remove(self, project_path: Path) -> None:
        normalized = self._normalize(project_path)
        paths = [
            path
            for path in self._read_paths()
            if self._normalize(Path(path)) != normalized
        ]
        self._write_paths(paths)

    def _read_paths(self) -> StringList:
        if not self.path.exists():
            return []

        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []

        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = data.get("recent_projects", [])
        else:
            return []

        return [item for item in items if isinstance(item, str)]

    def _write_paths(self, paths: StringList) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps({"recent_projects": paths}, indent=2),
                encoding="utf-8",
            )
        except OSError:
            return

    def _normalize(self, path: Path) -> Path:
        return Path(path).expanduser().resolve(strict=False)

    def _exists(self, path: Path) -> bool:
        try:
            return path.exists()
        except OSError:
            return False
