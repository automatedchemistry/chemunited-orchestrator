"""Import a project's Python files inside their package, as the runtime does.

Processes and their helper modules, dashboard hooks and ``draw/setup.py`` are
loaded by path. :func:`import_project_file` gives such a file the module name
its package structure implies, the same name the dashboard's
``load_project()`` gives it, so the file can use relative imports
(``from ._lib import x``).
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.machinery
import importlib.util
import os
import sys
import threading
from pathlib import Path
from types import ModuleType

__all__ = ["import_project_file"]

# Set on the packages this module creates, so later calls know they may drop them.
_CREATED_HERE = "__chemunited_project_package__"
_PRIVATE_PREFIX = "_chemunited_dir_"

_lock = threading.RLock()


def import_project_file(path: Path) -> ModuleType:
    """Execute the Python file at *path* inside its package and return it.

    A file inside a regular package gets its real dotted name: walking up from
    the file, every folder with an ``__init__.py`` is a package, and the first
    folder without one is the import root. ``protocols/React.py`` in a project
    is ``protocols.React``, the name the dashboard's ``load_project()`` gives
    it. Any other file becomes a member of a private package made from its own
    folder, so the files next to it can still be imported with
    ``from . import helpers``.

    The packages above the file are created without running their
    ``__init__.py``, so one broken protocol can't stop another file from
    loading. Each call executes the file afresh: modules an earlier call loaded
    under the same top-level package are dropped first, so edits to the file
    and to the modules it imports are picked up.

    A package that ``import <name>`` still returns (the standard library, an
    installed package, ChemUnited itself) is never replaced: a file inside it
    runs within it, and any other file whose name would shadow it raises
    ``ImportError``.

    The import root is on ``sys.path`` while the file runs, as it is while the
    runtime imports a project. The module stays in ``sys.modules`` (pydantic
    and ``inspect.getfile`` need it). If the file raises, it is removed again
    and the exception propagates unchanged.
    """
    path = Path(path).resolve()
    with _lock:
        importlib.invalidate_caches()
        located = _package_location(path)
        if located is None:
            folder = path.parent
            package = _private_package_name(folder)
            _forget(package)
            _register(_bare_package(package, folder))
            return _execute(f"{package}.{path.stem.replace('.', '_')}", path)

        root, name = located
        _prepare_parents(root, name, path)
        root_entry = str(root)
        sys.path.insert(0, root_entry)
        try:
            return _execute(name, path)
        finally:
            try:
                sys.path.remove(root_entry)
            except ValueError:
                pass


def _package_location(path: Path) -> tuple[Path, str] | None:
    """``(import root, dotted name)`` for a file inside a regular package."""
    is_init = path.name == "__init__.py"
    parts = [] if is_init else [path.stem]
    folder = path.parent
    while (folder / "__init__.py").is_file() and folder.parent != folder:
        parts.insert(0, folder.name)
        folder = folder.parent
    if len(parts) <= (0 if is_init else 1) or any("." in part for part in parts):
        return None
    return folder, ".".join(parts)


def _private_package_name(folder: Path) -> str:
    digest = hashlib.sha256(os.fsencode(os.path.normcase(str(folder)))).hexdigest()
    return f"{_PRIVATE_PREFIX}{digest[:16]}"


def _prepare_parents(root: Path, name: str, path: Path) -> None:
    """Make the packages above *name* importable, as their folders under *root*."""
    top = name.partition(".")[0]
    cached = sys.modules.get(top)
    if cached is not None and not getattr(cached, _CREATED_HERE, False):
        if _norm(root / top) in _locations(cached):
            # Imported the ordinary way from this very folder (by the runtime,
            # or ChemUnited's own files): run the file within that package.
            for parent in _parent_names(name):
                importlib.import_module(parent)
            return
        if _is_live(cached, top):
            raise ImportError(
                f"Cannot import {path} as {name!r}: {top!r} is already the "
                f"package at {', '.join(sorted(_locations(cached))) or 'built-in'}",
                name=name,
                path=str(path),
            )
        # Otherwise it's a leftover of an earlier project import that
        # `import <top>` no longer returns; the runtime drops those too.
    _forget(top)
    for parent in _parent_names(name):
        _register(_bare_package(parent, root.joinpath(*parent.split("."))))


def _parent_names(name: str) -> list[str]:
    parts = name.split(".")
    return [".".join(parts[:end]) for end in range(1, len(parts))]


def _bare_package(name: str, folder: Path) -> ModuleType:
    """A package whose submodules are found in *folder*; its ``__init__.py`` isn't run."""
    spec = importlib.machinery.ModuleSpec(name, None, is_package=True)
    spec.submodule_search_locations = [str(folder)]
    module = importlib.util.module_from_spec(spec)
    setattr(module, _CREATED_HERE, True)
    return module


def _execute(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot create a module spec from {path}", path=str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        if sys.modules.get(name) is module:
            del sys.modules[name]
        raise
    # A module may replace itself in sys.modules while it runs, as with import.
    module = sys.modules.get(name, module)
    _register(module, name)
    return module


def _register(module: ModuleType, name: str | None = None) -> None:
    """Put *module* in ``sys.modules`` and on its parent package, as import does."""
    name = name or module.__name__
    sys.modules[name] = module
    parent, _, child = name.rpartition(".")
    if parent and parent in sys.modules:
        setattr(sys.modules[parent], child, module)


def _forget(name: str) -> None:
    """Drop *name* and its submodules from ``sys.modules``."""
    prefix = f"{name}."
    for key in list(sys.modules):
        if key == name or key.startswith(prefix):
            sys.modules.pop(key, None)


def _is_live(module: ModuleType, name: str) -> bool:
    """Whether ``import <name>`` would still return *module*.

    Modules with no file to compare (built-in or frozen) always count as live.
    """
    locations = _locations(module)
    if not locations:
        return True
    spec = importlib.machinery.PathFinder.find_spec(name)
    if spec is None:
        return False
    if spec.submodule_search_locations is not None:
        found = {_norm(entry) for entry in spec.submodule_search_locations}
    else:
        found = {_norm(spec.origin)} if spec.origin else set()
    return not locations.isdisjoint(found)


def _locations(module: ModuleType) -> set[str]:
    """The folders a package searches, or the file a plain module came from."""
    search = getattr(module, "__path__", None)
    if search is not None:
        return {_norm(entry) for entry in search}
    file = getattr(module, "__file__", None)
    return {_norm(file)} if file else set()


def _norm(path: str | Path) -> str:
    return os.path.normcase(os.path.realpath(path))
