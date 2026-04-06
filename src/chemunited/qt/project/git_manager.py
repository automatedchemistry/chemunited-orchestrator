from __future__ import annotations

from pathlib import Path

import git  # gitpython

_GITIGNORE = """\
# Python
__pycache__/
*.pyc
*.pyo

# ChemUnited session
.chemunited_session
.chemunited_lock

# Connectivity is machine-specific
connectivity/associations.json

# OS
.DS_Store
Thumbs.db
"""


class GitManager:

    def __init__(self, repo: git.Repo):
        self._repo = repo

    # ── Setup ──────────────────────────────────────────────────────────────────

    @classmethod
    def init(cls, working_dir: Path) -> GitManager:
        """Initialize a fresh Git repo for a new project."""
        repo = git.Repo.init(working_dir)
        gitignore = working_dir / ".gitignore"
        gitignore.write_text(_GITIGNORE, encoding="utf-8")
        repo.index.add([".gitignore"])
        repo.index.commit("Initialize ChemUnited project")
        return cls(repo)

    @classmethod
    def init_from_import(cls, working_dir: Path, source_name: str) -> GitManager:
        """Initialize a fresh Git repo after unpacking a .chemunited file."""
        repo = git.Repo.init(working_dir)
        gitignore = working_dir / ".gitignore"
        gitignore.write_text(_GITIGNORE, encoding="utf-8")
        repo.index.add(["*"])
        repo.index.commit(f"Imported from {source_name}")
        return cls(repo)

    @classmethod
    def open(cls, working_dir: Path) -> GitManager | None:
        """Open existing repo, return None if not a Git project."""
        try:
            return cls(git.Repo(working_dir))
        except git.InvalidGitRepositoryError:
            return None

    # ── Auto-commit helpers (called by session on each save) ───────────────────

    def commit_draw(self) -> None:
        self._auto_commit(["draw/setup.json"], "Update platform layout")

    def commit_process(
        self,
        process: str,
        created: bool = False,
        deleted: bool = False,
    ) -> None:
        """Commit a process file and the auto-generated __init__.py registry."""
        if created:
            message = f"Add process: {process}"
        elif deleted:
            message = f"Remove process: {process}"
        else:
            message = f"Update process: {process}"
        # Always stage __init__.py alongside — it is regenerated on every change
        self._auto_commit(
            [f"protocols/{process}.py", "protocols/__init__.py"],
            message,
        )

    def commit_main_parameters(self) -> None:
        self._auto_commit(
            ["protocols/main_parameters.py"],
            "Update main parameters",
        )

    # ── Manual snapshot (user-facing) ──────────────────────────────────────────

    def snapshot(self, message: str) -> bool:
        """Stage everything and commit. Returns False if nothing to commit."""
        if not self._repo.is_dirty(untracked_files=True):
            return False
        self._repo.git.add(A=True)
        self._repo.index.commit(message)
        return True

    # ── Status (for GUI display) ───────────────────────────────────────────────

    def status(self) -> dict:
        return {
            "branch": self._repo.active_branch.name,
            "is_dirty": self._repo.is_dirty(untracked_files=True),
            "modified": [d.a_path for d in self._repo.index.diff(None)],
            "untracked": self._repo.untracked_files,
            "last_commit_message": self._repo.head.commit.message.strip(),
            "last_commit_time": (self._repo.head.commit.committed_datetime.isoformat()),
        }

    def log(self, max_entries: int = 20) -> list[dict]:
        return [
            {
                "sha": c.hexsha[:7],
                "message": c.message.strip(),
                "author": c.author.name,
                "time": c.committed_datetime.isoformat(),
            }
            for c in list(self._repo.iter_commits())[:max_entries]
        ]

    # ── Remote (GitHub / GitLab) ───────────────────────────────────────────────

    def set_remote(self, url: str, name: str = "origin") -> None:
        if name in [r.name for r in self._repo.remotes]:
            self._repo.delete_remote(name)
        self._repo.create_remote(name, url)

    def push(self, remote: str = "origin") -> None:
        self._repo.remote(remote).push()

    def pull(self, remote: str = "origin") -> None:
        self._repo.remote(remote).pull()

    def has_remote(self) -> bool:
        return len(self._repo.remotes) > 0

    # ── Internal ───────────────────────────────────────────────────────────────

    def _auto_commit(self, paths: list[str], message: str) -> None:
        """Stage specific paths and commit only if they changed."""
        existing = [p for p in paths if (Path(self._repo.working_dir) / p).exists()]
        if not existing:
            return
        self._repo.index.add(existing)
        if self._repo.is_dirty(index=True):
            self._repo.index.commit(message)
