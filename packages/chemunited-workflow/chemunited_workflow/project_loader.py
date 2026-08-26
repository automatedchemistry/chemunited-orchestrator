"""Load a chemunited project's protocols package from an arbitrary directory."""

from __future__ import annotations

import importlib
import sys
import threading
import traceback
from pathlib import Path
from typing import NamedTuple

from loguru import logger

_import_lock = threading.Lock()


class ProjectLoadError(ValueError):
    """Raised when a project directory cannot be loaded as a valid protocols package."""


class ProjectModules(NamedTuple):
    project_dir: Path
    processes: dict
    configs: dict
    main_parameter_class: type


def _relativize(path_str: str, project_dir: Path) -> str:
    try:
        return str(Path(path_str).relative_to(project_dir))
    except ValueError:
        return path_str


def format_broken_project_error(
    exc: BaseException, project_dir: Path, context: str
) -> str:
    """Format *exc* as `context` plus a traceback trimmed to frames inside *project_dir*.

    Also logs the full, untrimmed exception via loguru for server-side visibility.
    Must be called from inside the ``except`` block handling *exc*.
    """
    logger.exception(context)
    lines: list[str] = []

    if isinstance(exc, SyntaxError) and exc.filename:
        lines.append(
            f'  File "{_relativize(exc.filename, project_dir)}", line {exc.lineno}\n'
        )
        if exc.text:
            lines.append(f"    {exc.text.rstrip(chr(10))}\n")
            if exc.offset:
                lines.append(f"    {' ' * (exc.offset - 1)}^\n")
    else:
        te = traceback.TracebackException.from_exception(exc)
        for frame in te.stack:
            if not frame.filename.startswith(str(project_dir)):
                continue
            lines.append(
                f'  File "{_relativize(frame.filename, project_dir)}", '
                f"line {frame.lineno}, in {frame.name}\n"
            )
            if frame.line:
                lines.append(f"    {frame.line}\n")

    lines.append(f"{type(exc).__name__}: {exc}")
    return f"{context}:\n{''.join(lines)}"


def load_project(project_dir: Path) -> ProjectModules:
    """Import ``protocols/`` from *project_dir* and return the exported symbols.

    Raises
    ------
    ProjectLoadError
        If the required files are missing, imports fail, or exports are absent.
    """
    project_dir = project_dir.resolve()

    if not (project_dir / "protocols" / "__init__.py").exists():
        raise ProjectLoadError(
            f"No 'protocols/__init__.py' found in '{project_dir}'.\n"
            "Expected layout:\n"
            "  <project_dir>/\n"
            "    protocols/__init__.py         # must export CONFIGS and PROCESSES\n"
            "    protocols/main_parameters.py  # must export MainParameter"
        )
    if not (project_dir / "protocols" / "main_parameters.py").exists():
        raise ProjectLoadError(
            f"No 'protocols/main_parameters.py' found in '{project_dir}'."
        )

    str_dir = str(project_dir)
    with _import_lock:
        sys.path.insert(0, str_dir)
        importlib.invalidate_caches()
        try:
            for key in list(sys.modules):
                if key == "protocols" or key.startswith("protocols."):
                    del sys.modules[key]
            protocols = importlib.import_module("protocols")
            protocols_mp = importlib.import_module("protocols.main_parameters")
        except Exception as exc:
            raise ProjectLoadError(
                format_broken_project_error(
                    exc,
                    project_dir,
                    f"Failed to import 'protocols' from '{project_dir}'",
                )
            ) from exc
        finally:
            sys.path.remove(str_dir)

    for attr in ("PROCESSES", "CONFIGS"):
        if not hasattr(protocols, attr):
            raise ProjectLoadError(f"'protocols/__init__.py' does not export '{attr}'.")
    if not hasattr(protocols_mp, "MainParameter"):
        raise ProjectLoadError(
            "'protocols/main_parameters.py' does not export 'MainParameter'."
        )

    return ProjectModules(
        project_dir=project_dir,
        processes=protocols.PROCESSES,
        configs=protocols.CONFIGS,
        main_parameter_class=protocols_mp.MainParameter,
    )
