"""Project loader — discovers and imports a chemunited project folder or ZIP."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from chemunited_core.components import ComponentData
from chemunited_core.compounds import COMPOUNDS
from chemunited_core.figure_registry.project_loader import load_project_components
from chemunited_workflow.process import Process
from loguru import logger

from ..adapter.graph import compile_graph
from ..adapter.models import HydraulicGraph
from .builder import PlatformBuilder


@dataclass
class ProjectState:
    project_path: Path
    processes: dict[str, type[Process]]
    configs: dict[str, type]  # process name → ProcessConfig class
    components: dict[str, ComponentData]
    graph: HydraulicGraph
    reactions_map: dict | None = None


def _resolve_project_dir(path: Path) -> Path:
    """Return the project directory for any supported path type."""
    if path.is_dir():
        return path

    if path.suffix == ".chemunited":
        if not path.exists():
            raise FileNotFoundError(f"Project path not found: {path}")
        sibling = path.with_suffix("")
        if sibling.is_dir():
            return sibling
        if not zipfile.is_zipfile(path):
            raise ValueError(f"Not a valid ZIP archive: {path}")
        tmp = Path(tempfile.mkdtemp(prefix="chemunited_"))
        with zipfile.ZipFile(path) as zf:
            zf.extractall(tmp)
        return tmp

    if not path.exists():
        raise FileNotFoundError(f"Project path not found: {path}")
    raise ValueError(f"Path must be a directory or .chemunited file: {path}")


def _import_module_from_path(module_name: str, file_path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {file_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _clear_module_tree(module_name: str) -> None:
    """Remove a module and all child modules from Python's import cache."""
    prefix = f"{module_name}."
    for cached_name in tuple(sys.modules):
        if cached_name == module_name or cached_name.startswith(prefix):
            sys.modules.pop(cached_name, None)


def load_project(path: Path) -> ProjectState:
    """Load a chemunited project and compile its hydraulic graph.

    Raises
    ------
    FileNotFoundError
        If path or required project files are missing.
    ValueError
        If path is not a directory or .chemunited file, or the ZIP is invalid.
    AttributeError
        If setup.py lacks build_draw or protocols/__init__.py lacks PROCESSES.
    """
    project_dir = _resolve_project_dir(path)
    logger.info("Resolved project directory: {}", project_dir)

    custom_figures = load_project_components(project_dir)
    if custom_figures:
        logger.info("Custom components registered: {}", custom_figures)

    setup_path = project_dir / "draw" / "setup.py"
    if not setup_path.exists():
        raise FileNotFoundError(f"draw/setup.py not found in {project_dir}")

    protocols_init = project_dir / "protocols" / "__init__.py"
    if not protocols_init.exists():
        raise FileNotFoundError(f"protocols/__init__.py not found in {project_dir}")

    # Import draw/setup.py and run build_draw
    setup_module_name = f"_chemunited_draw_{project_dir.name}"
    logger.debug("Importing draw/setup.py from {}", setup_path)
    _clear_module_tree(setup_module_name)
    setup_module = _import_module_from_path(setup_module_name, setup_path)
    if not hasattr(setup_module, "build_draw"):
        raise AttributeError(f"setup.py in {project_dir} does not define build_draw")

    # Import protocols/__init__.py and read PROCESSES
    # Ensure protocols/ dir is on sys.path so relative imports inside work
    protocols_parent = str(project_dir)
    if protocols_parent not in sys.path:
        sys.path.insert(0, protocols_parent)

    protocols_module_name = f"_chemunited_protocols_{project_dir.name}"
    logger.debug("Importing protocols/__init__.py from {}", protocols_init)
    _clear_module_tree(protocols_module_name)
    protocols_module = _import_module_from_path(protocols_module_name, protocols_init)
    if not hasattr(protocols_module, "PROCESSES"):
        raise AttributeError(
            f"protocols/__init__.py in {project_dir} has no PROCESSES attribute"
        )

    processes: dict[str, type[Process]] = protocols_module.PROCESSES
    configs: dict[str, type] = getattr(protocols_module, "CONFIGS", {})
    logger.info("Processes available: {}", list(processes))

    COMPOUNDS.clear()
    builder = PlatformBuilder()
    logger.debug("Running build_draw()")
    setup_module.build_draw(builder)
    logger.info(
        "build_draw complete | components={} edges={}",
        len(builder.components),
        len(builder.edges),
    )

    logger.debug("Compiling hydraulic graph")
    graph = compile_graph(builder.components, builder.edges)

    if hasattr(setup_module, "build_graph_patch"):
        logger.debug("Applying build_graph_patch()")
        setup_module.build_graph_patch(graph)

    components = {c.name: c for c in builder.components}
    reactions_map = builder.reactions_map or None
    logger.info(
        "Project '{}' ready | {} component(s) | reactions_map={}",
        project_dir.name,
        len(components),
        reactions_map is not None,
    )

    return ProjectState(
        project_path=project_dir,
        processes=processes,
        configs=configs,
        components=components,
        graph=graph,
        reactions_map=reactions_map,
    )


def resolve_historical_file(project_dir: Path, filename: str | None) -> Path:
    """Return the Path for a historical_file argument.

    If filename is None, returns the most recently modified JSON in
    protocols_historic/. If filename is a basename, resolves it relative to
    protocols_historic/. If it is an absolute path, uses it directly.
    """
    historic_dir = project_dir / "protocols_historic"

    if filename is None:
        candidates = sorted(
            historic_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True
        )
        if not candidates:
            raise FileNotFoundError(f"No JSON files in {historic_dir}")
        chosen = candidates[0]
        logger.info("Auto-selected historical file: {}", chosen.name)
        return chosen

    candidate = Path(filename)
    if candidate.is_absolute():
        logger.info("Using absolute historical file: {}", candidate)
        return candidate
    resolved = historic_dir / filename
    logger.info("Using historical file: {}", resolved.name)
    return resolved


def parse_historical_file(path: Path) -> tuple[dict, list[tuple[str, dict]]]:
    """Parse a historical JSON file into (main_parameter, process_sequence).

    process_sequence is sorted by the integer suffix of each <Name>_<index> key.
    """
    logger.debug("Parsing historical file: {}", path.name)
    data: dict = json.loads(path.read_text(encoding="utf-8"))
    main_parameter = data.get("main_parameter", {})

    entries: list[tuple[int, str, dict]] = []
    for key, value in data.items():
        if key == "main_parameter":
            continue
        parts = key.rsplit("_", 1)
        if len(parts) == 2 and parts[1].isdigit():
            entries.append((int(parts[1]), parts[0], value))

    entries.sort(key=lambda e: e[0])
    process_sequence = [(name, kwargs) for _, name, kwargs in entries]
    logger.info(
        "Historical file '{}' parsed | {} process step(s): {}",
        path.name,
        len(process_sequence),
        [n for n, _ in process_sequence],
    )
    return main_parameter, process_sequence
