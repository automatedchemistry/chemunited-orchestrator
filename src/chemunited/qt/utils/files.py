import importlib.util
from pathlib import Path
from typing import Any


def load_class(file_path: Path, class_name: str) -> type[Any]:
    """
    Load a class from a Python file without importing the whole package.
    """
    spec = importlib.util.spec_from_file_location(class_name, file_path)
    if spec is None:
        raise ImportError(f"Could not load module {file_path}")
    loader = spec.loader
    if loader is None:
        raise ImportError(f"Could not load module {file_path}")
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    loaded = getattr(module, class_name)
    if not isinstance(loaded, type):
        raise TypeError(f"{class_name} in {file_path} is not a class")
    return loaded
