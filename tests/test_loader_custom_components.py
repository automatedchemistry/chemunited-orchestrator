"""Tests for chemunited_sim.cli.loader picking up project-local custom components.

Exercises the scenario the "build a custom component from your own project
folder" feature targets: a component defined and registered entirely inside a
project's components/ folder, with no chemunited-core source edits.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from chemunited_sim.cli.loader import load_project


def _write_protocols(project_dir: Path) -> None:
    protocols_dir = project_dir / "protocols"
    protocols_dir.mkdir(parents=True, exist_ok=True)
    (protocols_dir / "__init__.py").write_text("PROCESSES = {}\n", encoding="utf-8")


def _write_custom_component(project_dir: Path) -> None:
    components_dir = project_dir / "customizations" / "components"
    components_dir.mkdir(parents=True, exist_ok=True)
    (components_dir / "__init__.py").write_text(
        "from . import my_valve\n", encoding="utf-8"
    )
    (components_dir / "my_valve.py").write_text(
        textwrap.dedent("""
            from chemunited_core.components import ComponentData, ComponentMode
            from chemunited_core.figure_registry import (
                ComponentDefinition,
                register_component,
            )


            class MyValveMode(ComponentMode):
                pass


            class MyValveData(ComponentData):
                pass


            register_component("MyValve", ComponentDefinition(MyValveData, MyValveMode))
            """),
        encoding="utf-8",
    )


def test_load_project_registers_and_uses_custom_component(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    _write_protocols(project_dir)
    _write_custom_component(project_dir)

    draw_dir = project_dir / "draw"
    draw_dir.mkdir()
    (draw_dir / "setup.py").write_text(
        "def build_draw(platform):\n"
        '    platform.add_component(name="myvalve", figure="MyValve")\n',
        encoding="utf-8",
    )

    state = load_project(project_dir)

    assert "myvalve" in state.components
    assert type(state.components["myvalve"]).__name__ == "MyValveData"


def test_load_project_without_components_folder_still_works(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    _write_protocols(project_dir)

    draw_dir = project_dir / "draw"
    draw_dir.mkdir()
    (draw_dir / "setup.py").write_text(
        "def build_draw(platform):\n    pass\n", encoding="utf-8"
    )

    state = load_project(project_dir)

    assert state.components == {}
