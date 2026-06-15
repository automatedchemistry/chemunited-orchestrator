"""Compatibility shim; protocols have moved to chemunited_core.protocols."""

import importlib
import sys
import warnings

warnings.warn(
    "chemunited.elements.component.protocols is deprecated. "
    "Use chemunited_core.protocols instead.",
    DeprecationWarning,
    stacklevel=2,
)

from chemunited_core.protocols import *  # noqa: F401, F403
from chemunited_core.protocols import __all__  # noqa: F401

_SUBMODULES = (
    "analytics",
    "assembly",
    "models",
    "pumps",
    "sensors",
    "technical",
    "valves",
)

for _submodule in _SUBMODULES:
    sys.modules[f"{__name__}.{_submodule}"] = importlib.import_module(
        f"chemunited_core.protocols.{_submodule}"
    )
