from __future__ import annotations

import fnmatch
import tomllib
from pathlib import Path


def test_qt_shared_resources_are_packaged() -> None:
    project_root = Path(__file__).resolve().parents[1]
    pyproject = tomllib.loads((project_root / "pyproject.toml").read_text())
    package_data = pyproject["tool"]["setuptools"]["package-data"]
    patterns = package_data["chemunited.qt.shared.resources"]
    resources_dir = project_root / "src" / "chemunited" / "qt" / "shared" / "resources"

    resource_files = [
        path.relative_to(resources_dir).as_posix()
        for path in resources_dir.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    ]

    missing = [
        resource
        for resource in resource_files
        if resource != "__init__.py"
        and resource != "resources_rc.py"
        and not any(fnmatch.fnmatchcase(resource, pattern) for pattern in patterns)
    ]

    assert missing == []
