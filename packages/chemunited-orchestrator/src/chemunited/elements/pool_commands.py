"""Dispatch drained `log/pool/*.jsonl` command entries onto live canvas components.

A pool entry is one line written by the device client / simulator while a
command is issued: {"component": ..., "method": "PUT"/"GET"/..., "command": ...,
"params": {...}}. GET entries are status queries and never mutate component
state; PUT/POST entries are replayed through ComponentData.apply(), which
already no-ops safely on any command name a given component type doesn't
recognise.
"""

from __future__ import annotations

from loguru import logger

from chemunited_core.components.live_state import iter_apply_kwargs

from .access import Components


def apply_pool_command(components: Components, entry: dict) -> None:
    if entry.get("method") == "GET":
        return

    name = entry.get("component", "")
    component = components.get(name)
    if component is None:
        return

    command = entry.get("command", "")
    params = entry.get("params") or {}
    try:
        for call_kwargs in iter_apply_kwargs(command, params):
            component.inf.apply(command, **call_kwargs)
            component.graph.sync_visuals()
            component.graph.flash()
    except Exception:
        logger.opt(exception=True).debug(
            f"Pool command '{command}' failed to apply on component '{name}'"
        )
        return
