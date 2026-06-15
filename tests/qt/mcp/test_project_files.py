from __future__ import annotations

from pathlib import Path

import pytest

from chemunited.mcp.project_files import ProjectFileAccess


def _make_project(tmp_path: Path) -> Path:
    working_dir = tmp_path / "demo"
    (working_dir / "draw").mkdir(parents=True)
    (working_dir / "connectivity").mkdir()
    (working_dir / "protocols").mkdir()
    (working_dir / "manifest.json").write_text("{}", encoding="utf-8")
    (working_dir / "draw" / "setup.py").write_text("draw", encoding="utf-8")
    (working_dir / "connectivity" / "associations.json").write_text(
        "{}",
        encoding="utf-8",
    )
    (working_dir / "protocols" / "main_parameters.py").write_text(
        "params",
        encoding="utf-8",
    )
    (working_dir / "protocols" / "React.py").write_text("process", encoding="utf-8")
    (working_dir / "protocols" / "__init__.py").write_text("", encoding="utf-8")
    return working_dir


def test_list_files_exposes_only_allowed_project_files(tmp_path: Path):
    working_dir = _make_project(tmp_path)
    (working_dir / "log").mkdir()
    (working_dir / "log" / "run.log").write_text("secret", encoding="utf-8")
    access = ProjectFileAccess(lambda: working_dir)

    paths = {entry["path"] for entry in access.list_files()}

    assert "manifest.json" in paths
    assert "draw/setup.py" in paths
    assert "connectivity/associations.json" in paths
    assert "protocols/main_parameters.py" in paths
    assert "protocols/React.py" in paths
    assert "protocols/__init__.py" not in paths
    assert "log/run.log" not in paths


def test_read_and_write_allowed_project_file(tmp_path: Path):
    working_dir = _make_project(tmp_path)
    access = ProjectFileAccess(lambda: working_dir)

    assert access.read_file("draw/setup.py") == "draw"
    result = access.write_file("draw/setup.py", "updated")

    assert result == {"path": "draw/setup.py", "bytes": 7}
    assert (working_dir / "draw" / "setup.py").read_text(encoding="utf-8") == "updated"


def test_rejects_disallowed_paths(tmp_path: Path):
    working_dir = _make_project(tmp_path)
    access = ProjectFileAccess(lambda: working_dir)

    for path in [
        "../outside.py",
        "/manifest.json",
        "log/run.log",
        "protocols/__init__.py",
        "protocols/nested/React.py",
    ]:
        with pytest.raises(ValueError):
            access.read_file(path)


def test_protocol_write_refreshes_protocol_registry(tmp_path: Path):
    working_dir = _make_project(tmp_path)
    access = ProjectFileAccess(lambda: working_dir)

    access.write_file("protocols/NewProcess.py", "process")

    init_content = (working_dir / "protocols" / "__init__.py").read_text(
        encoding="utf-8",
    )
    assert "NewProcessProcess" in init_content
    assert '"NewProcess": NewProcessProcess' in init_content


def test_delete_only_normal_protocol_files(tmp_path: Path):
    working_dir = _make_project(tmp_path)
    access = ProjectFileAccess(lambda: working_dir)

    result = access.delete_file("protocols/React.py")

    assert result == {"path": "protocols/React.py", "deleted": True}
    assert not (working_dir / "protocols" / "React.py").exists()
    with pytest.raises(ValueError):
        access.delete_file("manifest.json")
