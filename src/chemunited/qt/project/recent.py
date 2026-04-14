from __future__ import annotations

import json
import tempfile
from pathlib import Path

try:
    from appdirs import user_data_dir
except ImportError:  # pragma: no cover - fallback for editable dev envs

    def user_data_dir(appname: str, appauthor: str | None = None) -> str:
        return str(Path(tempfile.gettempdir()) / appname)


APP_NAME = "ChemUnited Orchestrator"
APP_AUTHOR = "ChemUnited"
RECENT_PROJECTS_FILENAME = "recent_projects.json"
MAX_RECENT_PROJECTS = 10


def default_recent_projects_path() -> Path:
    return Path(user_data_dir(APP_NAME, APP_AUTHOR)) / RECENT_PROJECTS_FILENAME


class RecentProjectsStore:
    def __init__(self, path: Path | None = None, limit: int = MAX_RECENT_PROJECTS):
        self.path = path or default_recent_projects_path()
        self.limit = limit

    def list(self) -> list[Path]:
        return [Path(path) for path in self._read_paths()]

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

    def _read_paths(self) -> list[str]:
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

    def _write_paths(self, paths: list[str]) -> None:
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
