"""Loads project-local GraphComponent subclasses from components/graph.py.

Must run strictly after chemunited_core.figure_registry.project_loader's
load_project_components() has registered the project's custom figures, since
GraphComponent.__init_subclass__ requires FIGURE to already exist in
figure_registry.COMPONENTS at class-definition (i.e. import) time.

Kept separate from chemunited_core's component loader because this file
imports GraphComponent (PyQt5) — chemunited-sim's headless project loader
must never import it.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from chemunited_core.figure_registry.project_loader import (
    project_components_module_name,
)

from .graph_item import GraphComponent


def _import_module_from_path(module_name: str, file_path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {file_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def load_project_graph_components(project_dir: Path) -> dict[str, type[GraphComponent]]:
    """Import ``{project_dir}/components/graph.py`` if present.

    Returns {figure_name: GraphComponent subclass} for every GraphComponent
    subclass defined in that module (identified by its FIGURE attribute).
    Returns an empty dict if the project has no components/graph.py.
    """
    graph_path = project_dir / "components" / "graph.py"
    if not graph_path.exists():
        return {}

    # Load as a submodule of the already-imported components/ package so that
    # `from . import my_valve` inside graph.py resolves against the same
    # sibling modules load_project_components() already registered.
    module_name = f"{project_components_module_name(project_dir)}.graph"
    sys.modules.pop(module_name, None)
    module = _import_module_from_path(module_name, graph_path)

    result: dict[str, type[GraphComponent]] = {}
    for value in vars(module).values():
        if (
            isinstance(value, type)
            and issubclass(value, GraphComponent)
            and value is not GraphComponent
            and value.FIGURE
        ):
            result[value.FIGURE] = value
    return result
