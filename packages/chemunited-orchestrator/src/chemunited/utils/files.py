from pathlib import Path
from typing import Any

from chemunited_workflow.project_imports import import_project_file


def load_attribute(file_path: Path, attribute_name: str) -> Any:
    """
    Load an attribute from a project's Python file.

    The file is imported inside its package, under the name the runtime gives
    it (``protocols/React.py`` is ``protocols.React``), so its relative imports
    work; the package's ``__init__.py`` is not run. See
    :func:`chemunited_workflow.project_imports.import_project_file`.
    """
    return getattr(import_project_file(file_path), attribute_name)


def load_class(file_path: Path, class_name: str) -> Any:
    """
    Load a class from a project's Python file, imported inside its package.
    """
    return load_attribute(file_path, class_name)
