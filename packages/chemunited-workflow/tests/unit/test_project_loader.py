"""Unit tests for load_project() and its error reporting."""

from __future__ import annotations

from pathlib import Path

import pytest

from chemunited_workflow.project_loader import ProjectLoadError, load_project
from tests.helpers import write_source

VALID_INIT_SRC = """
PROCESSES = {}
CONFIGS = {}
"""

VALID_MAIN_PARAMETERS_SRC = """
class MainParameter:
    pass
"""

SYNTAX_ERROR_INIT_SRC = """
PROCESSES = {}
CONFIGS = {}

def broken(:
    pass
"""

NAME_ERROR_INIT_SRC = """
PROCESSES = {"x": undefined_name}
CONFIGS = {}
"""


def _make_protocols_dir(tmp_path: Path, init_src: str) -> Path:
    protocols_dir = tmp_path / "protocols"
    protocols_dir.mkdir()
    write_source(protocols_dir, "__init__.py", init_src)
    write_source(protocols_dir, "main_parameters.py", VALID_MAIN_PARAMETERS_SRC)
    return protocols_dir


def test_load_project_missing_protocols_init(tmp_path):
    with pytest.raises(ProjectLoadError, match="No 'protocols/__init__.py' found"):
        load_project(tmp_path)


def test_load_project_missing_main_parameters(tmp_path):
    protocols_dir = tmp_path / "protocols"
    protocols_dir.mkdir()
    write_source(protocols_dir, "__init__.py", VALID_INIT_SRC)
    with pytest.raises(
        ProjectLoadError, match="No 'protocols/main_parameters.py' found"
    ):
        load_project(tmp_path)


def test_load_project_success(tmp_path):
    _make_protocols_dir(tmp_path, VALID_INIT_SRC)
    modules = load_project(tmp_path)
    assert modules.project_dir == tmp_path.resolve()
    assert modules.processes == {}
    assert modules.configs == {}
    assert modules.main_parameter_class.__name__ == "MainParameter"


def test_load_project_syntax_error(tmp_path):
    _make_protocols_dir(tmp_path, SYNTAX_ERROR_INIT_SRC)
    with pytest.raises(ProjectLoadError) as exc_info:
        load_project(tmp_path)
    message = str(exc_info.value)
    assert "SyntaxError" in message
    assert str(Path("protocols") / "__init__.py") in message
    assert "line 5" in message


def test_load_project_name_error(tmp_path):
    _make_protocols_dir(tmp_path, NAME_ERROR_INIT_SRC)
    with pytest.raises(ProjectLoadError) as exc_info:
        load_project(tmp_path)
    message = str(exc_info.value)
    assert "NameError" in message
    assert "undefined_name" in message
    assert str(Path("protocols") / "__init__.py") in message
    assert "importlib" not in message
    assert "project_loader.py" not in message
