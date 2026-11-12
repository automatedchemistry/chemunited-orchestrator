"""Versioned protocol structure, independent of the API and execution engine."""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

PROTOCOL_SCHEMA_VERSION = 2


def decimal_string(value: int) -> str:
    """Serialize an exact nonnegative integer without Python's digit ceiling."""
    if value < 0:
        return "-" + decimal_string(-value)
    if value == 0:
        return "0"
    chunks = []
    while value:
        value, remainder = divmod(value, 1_000_000_000)
        chunks.append(remainder)
    return str(chunks[-1]) + "".join(f"{chunk:09d}" for chunk in reversed(chunks[:-1]))


def parse_decimal_string(value: Any, *, field: str, minimum: int = 0) -> int:
    """Require canonical ASCII decimal JSON strings, never floats or booleans."""
    if not isinstance(value, str) or re.fullmatch(r"0|[1-9][0-9]*", value) is None:
        raise ValueError(f"{field}: expected a canonical decimal string.")
    number = 0
    for start in range(0, len(value), 9):
        chunk = value[start : start + 9]
        number = number * (10 ** len(chunk)) + int(chunk)
    if number < minimum:
        requirement = "greater than 1" if minimum == 2 else f"at least {minimum}"
        raise ValueError(f"{field}: must be {requirement}.")
    return number


@dataclass(frozen=True)
class ProcessStep:
    id: str
    process: str
    parameters: dict[str, Any]
    legacy_key: str | None = None
    legacy_index: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "process",
            "id": self.id,
            "process": self.process,
            "parameters": deepcopy(self.parameters),
        }


@dataclass(frozen=True)
class RepeatGroup:
    id: str
    label: str
    count: int
    steps: tuple[ProcessStep, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "repeat",
            "id": self.id,
            "label": self.label,
            "count": decimal_string(self.count),
            "steps": [step.to_dict() for step in self.steps],
        }


@dataclass(frozen=True)
class ProtocolDocument:
    main_parameter: dict[str, Any]
    sequence: tuple[ProcessStep | RepeatGroup, ...]
    source_schema_version: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PROTOCOL_SCHEMA_VERSION,
            "main_parameter": deepcopy(self.main_parameter),
            "sequence": [item.to_dict() for item in self.sequence],
        }


def normalize_protocol_document(data: Any) -> ProtocolDocument:
    """Read v2 or flat legacy structure without inferring process semantics."""
    if not isinstance(data, dict):
        raise ValueError("Protocol: expected a JSON object.")
    main = data.get("main_parameter", {})
    if not isinstance(main, dict):
        raise ValueError("main_parameter: expected a JSON object.")

    if "schema_version" not in data:
        steps = []
        for key, parameters in data.items():
            if key == "main_parameter":
                continue
            match = (
                re.fullmatch(r"(.+)_([0-9]+)", key) if isinstance(key, str) else None
            )
            if match is None:
                raise ValueError(
                    f"Invalid protocol key '{key}'. Expected '{{process}}_{{index}}'."
                )
            if not isinstance(parameters, dict):
                raise ValueError(f"{key} / parameters: expected a JSON object.")
            # Legacy suffixes need not be canonical: preserve both the original
            # execution key and its numeric Process.process_index.
            index_text = match.group(2).lstrip("0") or "0"
            steps.append(
                ProcessStep(
                    id=key,
                    process=match.group(1),
                    parameters=deepcopy(parameters),
                    legacy_key=key,
                    legacy_index=parse_decimal_string(
                        index_text, field=f"{key} / index"
                    ),
                )
            )
        return ProtocolDocument(deepcopy(main), tuple(steps), 1)

    version = data["schema_version"]
    if type(version) is not int or version != PROTOCOL_SCHEMA_VERSION:
        raise ValueError(f"schema_version: unsupported protocol version {version!r}.")
    unexpected = set(data) - {"schema_version", "main_parameter", "sequence"}
    if unexpected:
        raise ValueError(f"Protocol: unsupported field {next(iter(unexpected))!r}.")
    sequence = data.get("sequence")
    if not isinstance(sequence, list):
        raise ValueError("sequence: expected a list of process steps or repeat groups.")

    seen: set[str] = set()

    def identity(item: dict[str, Any], where: str) -> str:
        source_id = item.get("id")
        if not isinstance(source_id, str) or not source_id.strip():
            raise ValueError(f"{where} / id: expected a nonempty stable source ID.")
        if source_id in seen:
            raise ValueError(f"{where} / id: duplicate source ID {source_id!r}.")
        seen.add(source_id)
        return source_id

    def process_step(item: dict[str, Any], where: str) -> ProcessStep:
        source_id = identity(item, where)
        where = f"{where} [{source_id}]"
        unexpected = set(item) - {"type", "id", "process", "parameters"}
        if unexpected:
            raise ValueError(f"{where}: unsupported field {next(iter(unexpected))!r}.")
        process_name = item.get("process")
        if not isinstance(process_name, str) or not process_name.strip():
            raise ValueError(f"{where} / process: expected a process registry name.")
        parameters = item.get("parameters", {})
        if not isinstance(parameters, dict):
            raise ValueError(f"{where} / parameters: expected a JSON object.")
        return ProcessStep(source_id, process_name, deepcopy(parameters))

    items: list[ProcessStep | RepeatGroup] = []
    for position, item in enumerate(sequence):
        where = f"sequence[{position}]"
        if not isinstance(item, dict):
            raise ValueError(f"{where}: expected a process step or repeat group.")
        item_type = item.get("type")
        if item_type == "process":
            items.append(process_step(item, where))
            continue
        if item_type != "repeat":
            raise ValueError(
                f"{where} [{item.get('id', '?')}] / type: unsupported {item_type!r}."
            )
        source_id = identity(item, where)
        label = item.get("label", "Repeat")
        if not isinstance(label, str):
            raise ValueError(f"{where} [{source_id}] / label: expected text.")
        where = f"{label or 'Repeat'} [{source_id}]"
        unexpected = set(item) - {"type", "id", "label", "count", "steps"}
        if unexpected:
            raise ValueError(f"{where}: unsupported field {next(iter(unexpected))!r}.")
        count = parse_decimal_string(
            item.get("count"), field=f"{where} / count", minimum=2
        )
        body = item.get("steps")
        if not isinstance(body, list) or not body:
            raise ValueError(
                f"{where} / steps: a repeat group needs at least one process."
            )
        body_steps = []
        for body_position, child in enumerate(body):
            child_where = f"{where} / steps[{body_position}]"
            if not isinstance(child, dict):
                raise ValueError(f"{child_where}: expected a process step.")
            if child.get("type") == "repeat":
                raise ValueError(
                    f"{where} / steps: nested repeat groups are not supported."
                )
            if child.get("type") != "process":
                raise ValueError(f"{child_where} / type: expected 'process'.")
            body_steps.append(process_step(child, child_where))
        items.append(RepeatGroup(source_id, label, count, tuple(body_steps)))
    return ProtocolDocument(deepcopy(main), tuple(items), PROTOCOL_SCHEMA_VERSION)
