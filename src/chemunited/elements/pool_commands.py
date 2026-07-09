"""Dispatch drained `log/pool/*.jsonl` command entries onto live canvas components.

A pool entry is one line written by the device client / simulator while a
command is issued: {"component": ..., "method": "PUT"/"GET"/..., "command": ...,
"params": {...}}. GET entries are status queries and never mutate component
state; PUT/POST entries are replayed through ComponentData.apply(), which
already no-ops safely on any command name a given component type doesn't
recognise.
"""

from __future__ import annotations

import json
from typing import Iterator

from loguru import logger

from .access import Components


def _normalize_connect_pairs(parsed: object) -> list[tuple[int, int]] | None:
    if not isinstance(parsed, list) or not parsed:
        return None
    # Flat pair: [a, b] - both elements are numbers, not nested lists.
    if len(parsed) == 2 and all(isinstance(x, (int, float)) for x in parsed):
        return [tuple(parsed)]  # type: ignore[list-item]
    # One or more pairs: [[a, b], ...] - every element is itself a 2-element list.
    if all(isinstance(item, list) and len(item) == 2 for item in parsed):
        return [tuple(item) for item in parsed]
    return None


def _iter_apply_kwargs(command: str, params: dict) -> Iterator[dict]:
    # PositionParameter.connect (chemunited_core.protocols.valves) is deliberately
    # str-typed for a GUI dropdown, and its JSON shape isn't consistent - a flat pair
    # "[a, b]" or a wrapped list of pairs "[[a, b]]"/"[[a, b], [c, d]]". apply() expects
    # a single flat pair, so detect the shape, unwrap, and iterate.
    if command == "position" and isinstance(params.get("connect"), str):
        try:
            parsed = json.loads(params["connect"])
        except (json.JSONDecodeError, ValueError, TypeError):
            parsed = None
        pairs = _normalize_connect_pairs(parsed)
        if pairs:
            for pair in pairs:
                yield {**params, "connect": pair}
            return
    yield params


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
        for call_kwargs in _iter_apply_kwargs(command, params):
            component.inf.apply(command, **call_kwargs)
            component.graph.sync_visuals()
            component.graph.flash()
    except Exception:
        logger.opt(exception=True).debug(
            f"Pool command '{command}' failed to apply on component '{name}'"
        )
        return
    
