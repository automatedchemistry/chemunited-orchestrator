"""Unit tests for provenance: the project's git state and the software versions."""

from __future__ import annotations

import platform
import shutil
import subprocess
from pathlib import Path

import pytest

from chemunited_workflow import provenance
from chemunited_workflow.provenance import read_git_state, read_head, software_versions

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not on PATH")


@pytest.fixture(autouse=True)
def _no_repository_above_the_test(tmp_path, monkeypatch):
    # The temp folder could itself sit inside a git repository.
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "init.defaultBranch=main",
            *args,
        ],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _repo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init")
    (root / "README.md").write_text("project\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "initial")
    return root


@needs_git
def test_a_clean_repository_at_the_project_root(tmp_path):
    project = _repo(tmp_path / "project")
    state = read_git_state(project)
    assert state is not None
    assert state.commit == _git(project, "rev-parse", "HEAD")
    assert state.branch == "main"
    assert state.dirty is False
    assert state.changed == ()
    assert state.captured_at


@needs_git
def test_uncommitted_files_make_the_project_dirty(tmp_path):
    project = _repo(tmp_path / "project")
    (project / "README.md").write_text("edited\n", encoding="utf-8")
    (project / "my protocol.py").write_text("x = 1\n", encoding="utf-8")
    state = read_git_state(project)
    assert state is not None
    assert state.dirty is True
    assert state.changed == ("README.md", "my protocol.py")


@needs_git
def test_the_work_servers_own_files_are_not_changes(tmp_path):
    project = _repo(tmp_path / "project")
    (project / "log" / "manifests").mkdir(parents=True)
    (project / "log" / "manifests" / "run.json").write_text("{}", encoding="utf-8")
    (project / "run.lock").write_text("{}", encoding="utf-8")
    # Bytecode of the process code the work-server imported.
    (project / "protocols" / "__pycache__").mkdir(parents=True)
    (project / "protocols" / "__pycache__" / "react.pyc").write_bytes(b"\0")
    state = read_git_state(project)
    assert state is not None
    assert state.dirty is False


@needs_git
def test_a_repository_in_a_parent_folder(tmp_path):
    root = _repo(tmp_path / "lab")
    project = root / "AGA"
    (project / "protocols").mkdir(parents=True)
    (project / "protocols" / "react.py").write_text("x = 1\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "add the project")

    # A change outside the project folder doesn't concern it...
    (root / "README.md").write_text("edited\n", encoding="utf-8")
    state = read_git_state(project)
    assert state is not None
    assert state.commit == _git(root, "rev-parse", "HEAD")
    assert state.dirty is False

    # ...one inside it does, named relative to the project folder.
    (project / "protocols" / "react.py").write_text("x = 2\n", encoding="utf-8")
    state = read_git_state(project)
    assert state is not None
    assert state.changed == ("protocols/react.py",)


@needs_git
def test_a_rename_lists_only_the_new_path(tmp_path):
    project = _repo(tmp_path / "project")
    _git(project, "mv", "README.md", "NOTES.md")
    state = read_git_state(project)
    assert state is not None
    assert state.changed == ("NOTES.md",)


@needs_git
def test_a_detached_head_has_no_branch(tmp_path):
    project = _repo(tmp_path / "project")
    _git(project, "checkout", "--detach")
    state = read_git_state(project)
    assert state is not None
    assert state.branch is None
    assert state.commit == _git(project, "rev-parse", "HEAD")


@needs_git
def test_a_failing_git_status_leaves_dirty_unknown(tmp_path, monkeypatch):
    project = _repo(tmp_path / "project")
    real_git = provenance._git

    def git_without_status(git, project_dir, *args):
        if args[0] == "status":
            return None, "fatal: boom"
        return real_git(git, project_dir, *args)

    monkeypatch.setattr(provenance, "_git", git_without_status)
    state = read_git_state(project)
    assert state is not None
    assert state.dirty is None
    assert state.changed == ()


@needs_git
def test_a_folder_outside_any_repository_has_no_git_state(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    assert read_git_state(project) is None
    assert read_head(project) is None


@needs_git
def test_a_repository_without_commits_has_no_git_state(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    _git(project, "init")
    assert read_git_state(project) is None


def test_without_git_on_path_there_is_no_git_state(tmp_path, monkeypatch):
    monkeypatch.setattr(provenance.shutil, "which", lambda name: None)
    assert read_git_state(tmp_path) is None
    assert read_head(tmp_path) is None


@needs_git
def test_read_head_follows_new_commits(tmp_path):
    project = _repo(tmp_path / "project")
    loaded = read_git_state(project)
    (project / "README.md").write_text("edited\n", encoding="utf-8")
    _git(project, "commit", "-am", "edit")
    assert loaded is not None
    head = read_head(project)
    assert head == _git(project, "rev-parse", "HEAD")
    assert head != loaded.commit


def test_software_versions_name_python_and_the_workflow_package():
    versions = software_versions()
    assert versions["python"] == platform.python_version()
    assert "chemunited-workflow" in versions
