from __future__ import annotations

import re
from pathlib import Path

import git  # type: ignore[import-not-found]  # gitpython
from loguru import logger

from chemunited.shared.enums import WindowCategory

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

# Execution logs are local run outputs
log/

# OS
.DS_Store
Thumbs.db
"""


def ensure_gitignore(working_dir: Path) -> None:
    gitignore = working_dir / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(_GITIGNORE, encoding="utf-8")
        return

    content = gitignore.read_text(encoding="utf-8")
    if "log/" in content.splitlines():
        return
    if content and not content.endswith("\n"):
        content += "\n"
    content += "\n# Execution logs are local run outputs\nlog/\n"
    gitignore.write_text(content, encoding="utf-8")


class GitManager:

    def __init__(self, repo: git.Repo):
        self._repo = repo

    # ── Setup ──────────────────────────────────────────────────────────────────

    @classmethod
    def init(cls, working_dir: Path) -> GitManager:
        """Initialize a fresh Git repo for a new project."""
        repo = git.Repo.init(working_dir)
        ensure_gitignore(working_dir)
        repo.index.add([".gitignore"])
        repo.index.commit("Initialize ChemUnited project")
        return cls(repo)

    @classmethod
    def init_from_import(cls, working_dir: Path, source_name: str) -> GitManager:
        """Initialize a fresh Git repo after unpacking a .chemunited file."""
        repo = git.Repo.init(working_dir)
        ensure_gitignore(working_dir)
        repo.index.add(["*"])
        repo.index.commit(f"Imported from {source_name}")
        return cls(repo)

    @classmethod
    def open(cls, working_dir: Path) -> GitManager | None:
        """Open existing repo, return None if not a Git project."""
        try:
            repo = git.Repo(working_dir)
        except git.InvalidGitRepositoryError:
            return None
        ensure_gitignore(working_dir)
        return cls(repo)

    # ── Auto-commit helpers (called by session on each save) ───────────────────

    def commit_draw(self) -> None:
        self._auto_commit(
            ["draw/setup.py", "draw/platform.svg"],
            "Update platform layout",
        )

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
        try:
            if not self._repo.is_dirty(untracked_files=True):
                return False
            self._repo.git.add(A=True)
            self._repo.index.commit(message)
        except git.GitCommandError as exc:
            self._warn_commit_skipped("manual snapshot", exc)
            return False
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
        existing_remote = next(
            (remote for remote in self._repo.remotes if remote.name == name),
            None,
        )
        if existing_remote is not None:
            self._repo.delete_remote(existing_remote)
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
        try:
            root = Path(self._repo.working_dir)
            tracked = set(self._repo.git.ls_files("--", *paths).splitlines())
            stageable = [p for p in paths if (root / p).exists() or p in tracked]
            if not stageable:
                return
            self._repo.git.add("--", *stageable)
            if self._repo.is_dirty(index=True):
                self._repo.index.commit(message)
        except git.GitCommandError as exc:
            self._warn_commit_skipped(message, exc)

    def _warn_commit_skipped(self, action: str, exc: git.GitCommandError) -> None:
        logger.bind(window=WindowCategory.SETUP).warning(
            "Git commit skipped for {!r}: {}",
            action,
            self._git_error_reason(exc),
        )

    @staticmethod
    def _git_error_reason(exc: git.GitCommandError) -> str:
        output = "\n".join(
            part.strip()
            for part in (getattr(exc, "stderr", ""), getattr(exc, "stdout", ""))
            if part and part.strip()
        ).replace("\r\n", "\n")

        if not output:
            output = str(exc).strip()

        if "detected dubious ownership" in output:
            safe_directory_hint = re.search(
                r"git config --global --add safe\.directory\s+(.+)",
                output,
            )
            reason = (
                "Git does not trust this repository because it is owned by another "
                "user or group."
            )
            if safe_directory_hint is not None:
                return (
                    f"{reason} To trust it, run: "
                    f"git config --global --add safe.directory "
                    f"{safe_directory_hint.group(1).strip()}"
                )
            return reason

        lines = [line.strip() for line in output.splitlines() if line.strip()]
        return " ".join(lines[:4]) if lines else "Unknown Git error."
