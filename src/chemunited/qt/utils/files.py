import importlib.util
from pathlib import Path


def load_class(file_path: Path, class_name: str):
    """
    Load a class from a Python file without importing the whole package.
    """
    spec = importlib.util.spec_from_file_location(class_name, file_path)
    if spec is None:
        raise ImportError(f"Could not load module {file_path}")
    module = importlib.util.module_from_spec(spec)
    if module is None:
        raise ImportError(f"Could not load module {file_path}")
    spec.loader.exec_module(module)
    return getattr(module, class_name)
