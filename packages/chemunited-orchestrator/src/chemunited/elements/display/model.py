"""LcdDisplay — an LCD readout on the platform drawing, bound to a device variable."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

from chemunited_core.protocols import get_protocol_class
from chemunited_quantities import ChemUnitQuantity

# The work-server's pseudo-device for the project's custom monitoring sources:
# the functions in CUSTOM_SOURCES of customizations/monitoring/monitoring_hook.py.
CUSTOM_COMPONENT = "custom"


class LcdDisplay(BaseModel):
    """What ``platform.add_display(...)`` in ``draw/setup.py`` records.

    On the dashboard's live view the LCD shows the latest monitoring reading
    of ``component``'s ``command`` (with ``kwargs``), followed by ``unit`` when
    the reading is a number. ``component`` is a device, or ``"custom"`` for
    one of the project's custom monitoring sources. LCDs never read a device
    themselves, and aren't devices: no connectivity, no simulation.
    """

    name: str
    position: tuple[float, float] = (0.0, 0.0)
    component: str
    command: str
    kwargs: dict[str, Any] = Field(default_factory=dict)
    unit: str = ""

    @field_validator("name", "component", "command")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("unit")
    @classmethod
    def _stripped(cls, value: str) -> str:
        return value.strip()


def _json_value(value: Any) -> Any:
    if isinstance(value, ChemUnitQuantity):
        return str(value)
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def device_variables(figure: str, name: str) -> dict[str, dict[str, Any]]:
    """The variables an LCD can show for a device: its protocol's GET commands.

    Maps each command to its parameters' defaults, read from the device's
    protocol definition in chemunited-core, so no device has to be connected.
    """
    protocol = get_protocol_class(figure)(name).sync()
    return {
        signature.command: {
            key: _json_value(value) for key, value in signature.parameters.items()
        }
        for signature in protocol.get_commands.values()
    }


_SOURCES_NAME = "CUSTOM_SOURCES"
_DICT_MUTATORS = frozenset({"update", "pop", "popitem", "setdefault", "clear"})


def _is_sources(node: ast.AST) -> bool:
    return isinstance(node, ast.Name) and node.id == _SOURCES_NAME


def _changes_sources(node: ast.AST) -> bool:
    """Whether *node* assigns, deletes or edits ``CUSTOM_SOURCES``."""
    if isinstance(node, (ast.Name, ast.Subscript)):
        target = node if isinstance(node, ast.Name) else node.value
        return _is_sources(target) and isinstance(node.ctx, (ast.Store, ast.Del))
    if isinstance(node, ast.Attribute):
        return _is_sources(node.value) and node.attr in _DICT_MUTATORS
    return False


def _sources_value(tree: ast.Module) -> ast.expr | None:
    """What the hook assigns to ``CUSTOM_SOURCES`` at its top level."""
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        if any(_is_sources(target) for target in targets):
            return node.value
    return None


def custom_sources(project_dir: Path) -> tuple[str, ...] | None:
    """The names in ``CUSTOM_SOURCES`` of the project's monitoring hook.

    Read from the source, never run: the hook imports chemunited-workflow and
    may talk to devices. ``()`` without a hook; None when the names can't be
    read without running it: a syntax error, or anything but one dict literal
    with string keys that nothing else changes.
    """
    path = project_dir / "customizations" / "monitoring" / "monitoring_hook.py"
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ()
    except (OSError, ValueError, SyntaxError):
        return None
    if sum(_changes_sources(node) for node in ast.walk(tree)) != 1:
        return None
    value = _sources_value(tree)
    if not isinstance(value, ast.Dict):
        return None
    names = [
        key.value
        for key in value.keys
        if isinstance(key, ast.Constant) and isinstance(key.value, str)
    ]
    return tuple(names) if len(names) == len(value.keys) else None
