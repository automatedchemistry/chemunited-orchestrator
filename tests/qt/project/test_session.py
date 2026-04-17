from __future__ import annotations

import json
import zipfile

import pytest

from chemunited.qt.project.manifest import ProjectManifest
from chemunited.qt.project.session import ProjectSession


def _write_project(working_dir, draw_content: str) -> None:
    working_dir.mkdir(parents=True, exist_ok=True)
    ProjectManifest(
        name=working_dir.name,
        chemunited_version="0.1.0",
    ).save(working_dir)
    draw_path = working_dir / "draw" / "setup.py"
    draw_path.parent.mkdir(parents=True, exist_ok=True)
    draw_path.write_text(draw_content, encoding="utf-8")


def _write_archive(archive_path, project_name: str, draw_content: str) -> None:
    manifest = {
        "name": project_name,
        "chemunited_version": "0.1.0",
        "processes_order": [],
    }
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr("draw/setup.py", draw_content)


def test_import_chemunited_prefers_existing_project_directory(tmp_path):
    archive_path = tmp_path / "demo.chemunited"
    working_dir = tmp_path / "demo"
    local_draw = "# local project folder\n"
    archived_draw = "# archived export\n"
    _write_archive(archive_path, "demo", archived_draw)
    _write_project(working_dir, local_draw)

    session = ProjectSession()
    session.import_chemunited(archive_path)

    assert session.working_dir == working_dir
    assert session.source_file == archive_path
    assert (working_dir / "draw" / "setup.py").read_text(encoding="utf-8") == local_draw


def test_import_chemunited_does_not_overwrite_existing_non_project_path(tmp_path):
    archive_path = tmp_path / "demo.chemunited"
    working_dir = tmp_path / "demo"
    notes_path = working_dir / "notes.txt"
    _write_archive(archive_path, "demo", "# archived export\n")
    working_dir.mkdir()
    notes_path.write_text("keep me", encoding="utf-8")

    session = ProjectSession()
    with pytest.raises(FileExistsError):
        session.import_chemunited(archive_path)

    assert notes_path.read_text(encoding="utf-8") == "keep me"
    assert not (working_dir / "draw" / "setup.py").exists()
