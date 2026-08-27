import importlib.util
import sys
from pathlib import Path


def _module_name_for_path(file_path: Path, fallback: str) -> str:
    resolved = file_path.resolve()
    parts = list(resolved.parts)
    if "chemunited_core" in parts:
        start = parts.index("chemunited_core")
        module_parts = parts[start:-1] + [resolved.stem]
        return ".".join(module_parts)
    return fallback


def load_attribute(file_path: Path, attribute_name: str, fallback: str | None = None):
    """Load an attribute from a Python file without importing the whole package."""
    module_name = _module_name_for_path(file_path, fallback or attribute_name)
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None:
        raise ImportError(f"Could not load module {file_path}")
    loader = spec.loader
    if loader is None:
        raise ImportError(f"Could not load module {file_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    loader.exec_module(module)
    return getattr(module, attribute_name)


def load_class(file_path: Path, class_name: str):
    """Load a class from a Python file without importing the whole package."""
    return load_attribute(file_path, class_name)
