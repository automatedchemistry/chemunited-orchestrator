"""Unit tests for import_project_file(): project files load inside their package."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from textwrap import dedent

import pytest

from chemunited_workflow.project_imports import import_project_file
from chemunited_workflow.project_loader import load_project


@pytest.fixture(autouse=True)
def _forget_project_packages():
    """Drop the `protocols` package each test imports, so tests stay independent."""
    yield
    for name in list(sys.modules):
        if name == "protocols" or name.startswith("protocols."):
            del sys.modules[name]


def _write(path: Path, source: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(source).lstrip(), encoding="utf-8")
    return path


def _write_project(project: Path, limit: int = 9) -> Path:
    """A project whose process imports a nested helper package, as AGA's do."""
    protocols = project / "protocols"
    _write(
        protocols / "__init__.py",
        """
        from .Wash import CustomProcess as WashProcess, ProcessConfig as WashConfig

        PROCESSES = {"Wash": WashProcess}
        CONFIGS = {"Wash": WashConfig}
        """,
    )
    _write(
        protocols / "main_parameters.py",
        """
        from pydantic import BaseModel


        class MainParameter(BaseModel):
            operator: str = "lab"
        """,
    )
    _write(protocols / "_lib" / "__init__.py", "")
    _write(protocols / "_lib" / "hardware.py", f"LIMIT = {limit}\n")
    _write(
        protocols / "_lib" / "commands.py",
        """
        from . import hardware


        def limit():
            return hardware.LIMIT
        """,
    )
    return _write(
        protocols / "Wash.py",
        """
        from pydantic import BaseModel

        from ._lib.commands import limit


        class ProcessConfig(BaseModel):
            cycles: int = 2


        class CustomProcess:
            pass
        """,
    )


def test_relative_imports_work_and_names_match_the_runtime(tmp_path):
    wash = _write_project(tmp_path)

    module = import_project_file(wash)

    assert module.limit() == 9
    assert module.__name__ == "protocols.Wash"
    assert module.__package__ == "protocols"
    assert sys.modules["protocols.Wash"] is module

    runtime = load_project(tmp_path)
    main_parameters = import_project_file(tmp_path / "protocols" / "main_parameters.py")

    assert runtime.configs["Wash"].__module__ == module.__name__
    assert main_parameters.__name__ == runtime.main_parameter_class.__module__


def test_folder_names_do_not_matter(tmp_path):
    before = sys.modules.get("chemunited")
    wash = _write_project(tmp_path / "chemunited" / "demo")

    module = import_project_file(wash)

    assert module.__name__ == "protocols.Wash"
    assert module.limit() == 9
    assert sys.modules.get("chemunited") is before


def test_a_broken_package_init_does_not_stop_a_file_from_loading(tmp_path):
    wash = _write_project(tmp_path)
    _write(tmp_path / "protocols" / "__init__.py", "raise RuntimeError('broken')\n")

    assert import_project_file(wash).limit() == 9


def test_each_call_picks_up_edits_to_imported_modules(tmp_path):
    wash = _write_project(tmp_path, limit=9)
    assert import_project_file(wash).limit() == 9

    hardware = _write(tmp_path / "protocols" / "_lib" / "hardware.py", "LIMIT = 12\n")
    later = hardware.stat().st_mtime + 2.0
    os.utime(hardware, (later, later))

    assert import_project_file(wash).limit() == 12


def test_switching_projects_loads_the_other_project(tmp_path):
    first = _write_project(tmp_path / "first", limit=1)
    second = _write_project(tmp_path / "second", limit=2)

    assert import_project_file(first).limit() == 1
    assert import_project_file(second).limit() == 2
    assert list(sys.modules["protocols"].__path__) == [str(second.parent.resolve())]


def test_replaces_a_project_package_the_runtime_left_behind(tmp_path):
    _write_project(tmp_path / "first", limit=1)
    second = _write_project(tmp_path / "second", limit=2)
    load_project(tmp_path / "first")

    assert import_project_file(second).limit() == 2


def test_a_file_outside_any_package_can_import_its_neighbours(tmp_path):
    hook_dir = tmp_path / "customizations" / "routers"
    _write(hook_dir / "helpers.py", "VALUE = 42\n")
    hook = _write(hook_dir / "router_hook.py", "from .helpers import VALUE\n")

    module = import_project_file(hook)

    assert module.VALUE == 42
    assert module.__package__
    assert Path(module.__file__) == hook.resolve()


def test_a_file_that_raises_is_not_left_behind(tmp_path):
    wash = _write_project(tmp_path)
    _write(wash, "from ._lib.commands import limit\nraise RuntimeError('boom')\n")
    path_before = list(sys.path)

    with pytest.raises(RuntimeError, match="boom"):
        import_project_file(wash)

    assert "protocols.Wash" not in sys.modules
    assert sys.path == path_before


def test_never_shadows_a_package_python_already_imports(tmp_path):
    stdlib_json = sys.modules["json"]
    _write(tmp_path / "json" / "__init__.py", "")
    clash = _write(tmp_path / "json" / "tools.py", "VALUE = 1\n")

    with pytest.raises(ImportError, match="'json' is already the package"):
        import_project_file(clash)

    assert sys.modules["json"] is stdlib_json
    assert json.dumps({}) == "{}"
