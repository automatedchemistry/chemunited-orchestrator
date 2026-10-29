"""Provenance: the project's git commit and the software a run executed with.

ChemUnited never commits anything; versioning a project is up to its users.
When the project is in a git repository (its own, or one in a parent
folder), the work-server reads its commit when it loads the project. That is
when the project's process code is imported, so it is the code every run of
that load executes. Without git on PATH, outside a repository, or in a
repository git refuses to read (another user's, say), there is no commit to
record.

Read-only: no git command here takes a lock or changes the repository.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess  # nosec B404
from dataclasses import dataclass
from datetime import datetime
from functools import cache
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from loguru import logger

GIT_TIMEOUT_SECONDS = 10
# Written into the project by the work-server itself, so never a change to it:
# its logs and run lock, and the bytecode of the process code it imports.
_RUNTIME_PATHSPECS = (
    ":(exclude)log",
    ":(exclude)run.lock",
    ":(exclude,glob)**/__pycache__/**",
)
_PACKAGES = ("chemunited-workflow", "chemunited-quantities", "chemunited-core")


@dataclass(frozen=True)
class GitState:
    """The project's git state, read when the project was loaded."""

    commit: str
    # None when HEAD is detached.
    branch: str | None
    # None when git status failed, so whether files changed is unknown.
    dirty: bool | None
    # Uncommitted files, relative to the project folder.
    changed: tuple[str, ...]
    captured_at: str


def _git(git: str, project_dir: Path, *args: str) -> tuple[str | None, str]:
    """``(output, "")`` for a git command that succeeded, ``(None, reason)`` otherwise."""
    try:
        result = subprocess.run(  # nosec B603
            [git, "-c", "core.quotePath=false", "-C", str(project_dir), *args],
            capture_output=True,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
            # Keep git status from refreshing, and so locking, the index.
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
            # The work-server runs from a tray icon: no console window per call.
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, str(exc)
    if result.returncode != 0:
        lines = [line.strip() for line in result.stderr.splitlines() if line.strip()]
        return None, lines[0] if lines else f"git exited with {result.returncode}"
    return result.stdout, ""


def _changed_files(git: str, project_dir: Path) -> tuple[str, ...] | None:
    """Uncommitted files under the project folder, or None if git status failed."""
    # Porcelain paths are relative to the repository root, which can be a
    # parent of the project folder.
    prefix, reason = _git(git, project_dir, "rev-parse", "--show-prefix")
    status = None
    if prefix is not None:
        status, reason = _git(
            git,
            project_dir,
            "status",
            "--porcelain=v1",
            "-z",
            "--",
            ".",
            *_RUNTIME_PATHSPECS,
        )
    if prefix is None or status is None:
        logger.info("Could not read the git status of {}: {}", project_dir, reason)
        return None
    prefix = prefix.strip()
    changed = []
    # With -z a rename or copy is "XY new\0old\0": skip the old path.
    entries = iter(status.split("\0"))
    for entry in entries:
        if not entry:
            continue
        code, path = entry[:2], entry[3:]
        if "R" in code or "C" in code:
            next(entries, None)
        changed.append(path.removeprefix(prefix))
    return tuple(sorted(changed))


def read_head(project_dir: Path) -> str | None:
    """The commit HEAD points at now, or None without git or a commit."""
    git = shutil.which("git")
    if git is None:
        return None
    head, _ = _git(git, project_dir, "rev-parse", "--verify", "HEAD")
    return None if head is None else head.strip()


def read_git_state(project_dir: Path) -> GitState | None:
    """The project's commit, branch and uncommitted files, or None without git.

    Never raises: whatever keeps git from answering is logged and gives None.
    """
    git = shutil.which("git")
    if git is None:
        logger.info(
            "Git is not installed or not on PATH: runs of {} record no commit.",
            project_dir,
        )
        return None
    head, reason = _git(git, project_dir, "rev-parse", "--verify", "HEAD")
    if head is None:
        logger.info("No git commit to record for {}: {}", project_dir, reason)
        return None
    branch, _ = _git(git, project_dir, "branch", "--show-current")
    changed = _changed_files(git, project_dir)
    return GitState(
        commit=head.strip(),
        branch=(branch or "").strip() or None,
        dirty=None if changed is None else bool(changed),
        changed=changed or (),
        captured_at=datetime.now().astimezone().isoformat(timespec="seconds"),
    )


@cache
def software_versions() -> dict[str, str]:
    """Python's version and the ChemUnited packages' versions.

    Read once: packages upgraded on disk while the work-server runs don't
    change the code it has loaded, which is what runs execute.
    """
    versions = {"python": platform.python_version()}
    for name in _PACKAGES:
        try:
            versions[name] = version(name)
        except PackageNotFoundError:
            continue
    return versions
