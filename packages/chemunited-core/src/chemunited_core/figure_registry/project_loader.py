"""Loads project-local custom components into the shared COMPONENTS registry.

See ``register_component`` (in ``chemunited_core.figure_registry``) for the API a
project's component modules are expected to call. This module only handles
discovering and importing ``{project_dir}/customizations/components/__init__.py``
as a real Python package, so that relative imports between a project's own
component modules work normally (e.g. ``from . import my_valve``).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from chemunited_core.figure_registry import (
    COMPONENTS,
    clear_project_components,
    register_figure,
)
from chemunited_core.protocols import clear_project_protocols


def project_components_module_name(project_dir: Path) -> str:
    """Deterministic synthetic module name for a project's components/ package.

    Shared with chemunited-orchestrator's project-local GraphComponent loader
    so that ``customizations/components/graph.py`` can resolve
    ``from . import <sibling>`` against the same package this module already
    imported.
    """
    return f"_chemunited_components_{project_dir.name}"


def _clear_module_tree(module_name: str) -> None:
    """Remove a module and all child modules from Python's import cache."""
    prefix = f"{module_name}."
    for cached_name in tuple(sys.modules):
        if cached_name == module_name or cached_name.startswith(prefix):
            sys.modules.pop(cached_name, None)


def _import_package_from_path(module_name: str, init_path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        module_name,
        init_path,
        submodule_search_locations=[str(init_path.parent)],
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {init_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def load_project_components(project_dir: Path) -> list[str]:
    """Import ``{project_dir}/customizations/components/__init__.py`` if present.

    The file is expected to import whatever sibling modules define custom
    components (e.g. ``from . import my_valve``), each of which calls
    ``register_component()`` and, if commandable, ``register_protocol()`` at
    module level as an import side effect.

    Returns the list of figure names newly added to COMPONENTS, for logging.
    Returns an empty list if the project has no ``customizations/components/``
    folder.
    """
    clear_project_components()
    clear_project_protocols()

    components_init = project_dir / "customizations" / "components" / "__init__.py"
    if not components_init.exists():
        return []

    project_dir_str = str(project_dir)
    if project_dir_str not in sys.path:
        sys.path.insert(0, project_dir_str)

    module_name = project_components_module_name(project_dir)
    _clear_module_tree(module_name)

    before = set(COMPONENTS)
    _import_package_from_path(module_name, components_init)

    # Make every SVG in customizations/components/ discoverable by filename,
    # not just the ones
    # register_component() already auto-resolved for a specific figure. Covers
    # auxiliary/composited layers a custom GraphComponent references directly
    # (e.g. self._build_svg("MyValveHandle")) with no figure of their own.
    for svg_path in components_init.parent.glob("*.svg"):
        register_figure(svg_path.stem, svg_path, override=True)

    return sorted(set(COMPONENTS) - before)
