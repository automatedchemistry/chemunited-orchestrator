from __future__ import annotations

from dataclasses import dataclass

import git
from loguru import logger

from chemunited.project.git_manager import GitManager


@dataclass
class _FailingGit:
    stderr: str

    def ls_files(self, *_args: str) -> str:
        raise git.GitCommandError(
            ["git", "ls-files"],
            128,
            stderr=self.stderr,
        )


@dataclass
class _FailingRepo:
    working_dir: str
    git: _FailingGit


def test_auto_commit_warns_when_git_rejects_dubious_ownership(tmp_path):
    messages: list[str] = []
    sink_id = logger.add(
        lambda message: messages.append(message.record["message"]),
        level="WARNING",
    )
    stderr = """
fatal: detected dubious ownership in repository at '//server/share/project'
To add an exception for this directory, call:

        git config --global --add safe.directory '%(prefix)///server/share/project'
""".strip()
    manager = GitManager(_FailingRepo(str(tmp_path), _FailingGit(stderr)))  # type: ignore[arg-type]

    try:
        manager._auto_commit(["draw/setup.py"], "Update platform layout")
    finally:
        logger.remove(sink_id)

    assert len(messages) == 1
    assert "Git commit skipped for 'Update platform layout'" in messages[0]
    assert "owned by another user or group" in messages[0]
    assert "git config --global --add safe.directory" in messages[0]
