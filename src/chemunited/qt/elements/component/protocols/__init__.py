"""Compatibility shim — protocols have moved to chemunited_core.protocols."""
import warnings

warnings.warn(
    "chemunited.qt.elements.component.protocols is deprecated. "
    "Use chemunited_core.protocols instead.",
    DeprecationWarning,
    stacklevel=2,
)

from chemunited_core.protocols import *  # noqa: F401, F403
from chemunited_core.protocols import __all__  # noqa: F401
