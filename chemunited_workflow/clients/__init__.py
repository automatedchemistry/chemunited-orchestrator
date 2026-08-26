"""Device client hierarchy: HTTP (flowchem) always available; SiLA2/OPC UA optional.

``SilaComponentClient`` and ``OpcUaComponentClient`` require the ``sila2``/
``asyncua`` extras (``pip install chemunited-workflow[sila2]`` /
``[opcua]``) and are imported lazily on first access so a flowchem-only
install never imports gRPC/asyncua at all.
"""

from __future__ import annotations

from importlib import import_module

from .base import (
    DeviceClientMixin,
    _pop_thread_resilient_errors as _pop_thread_resilient_errors,
)
from .envelope import CommandResponse
from .http import BaseClient, ComponentClient

__all__ = [
    "BaseClient",
    "ComponentClient",
    "CommandResponse",
    "DeviceClientMixin",
    "SilaComponentClient",
    "OpcUaComponentClient",
]

_OPTIONAL_CLIENTS: dict[str, tuple[str, str, str]] = {
    "SilaComponentClient": ("sila2", ".sila", "SilaComponentClient"),
    "OpcUaComponentClient": ("asyncua", ".opcua", "OpcUaComponentClient"),
}


def __getattr__(name: str):
    if name in _OPTIONAL_CLIENTS:
        extra, module_name, attr = _OPTIONAL_CLIENTS[name]
        try:
            module = import_module(module_name, __name__)
        except ImportError as exc:
            raise ImportError(
                f"{name} requires the '{extra}' package. Install it with "
                f"'pip install chemunited-workflow[{extra}]'."
            ) from exc
        value = getattr(module, attr)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
