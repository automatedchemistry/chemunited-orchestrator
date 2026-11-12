"""Compact, validated protocol plans with lazy execution and arithmetic previews."""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Iterator, Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from .protocol_document import (
    PROTOCOL_SCHEMA_VERSION,
    ProcessStep,
    RepeatGroup,
    decimal_string,
    normalize_protocol_document,
    parse_decimal_string,
)

PLANNER_VERSION = 1
MAX_PREVIEW_LIMIT = 200


@dataclass(frozen=True)
class ProcessOccurrence:
    execution_key: str
    process_name: str
    process_index: int
    parameters: dict[str, Any]
    main_parameters: dict[str, Any]
    source_id: str
    group_id: str | None
    label: str | None
    cycle: int | None
    count: int | None
    execution_index: int

    def metadata(self) -> dict[str, Any]:
        """JSON-safe identity and cycle attribution for events and results."""
        return {
            "execution_key": self.execution_key,
            "process_name": self.process_name,
            "source_id": self.source_id,
            "group_id": self.group_id,
            "group_label": self.label,
            "cycle": decimal_string(self.cycle) if self.cycle is not None else None,
            "count": decimal_string(self.count) if self.count is not None else None,
            "execution_index": decimal_string(self.execution_index),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.metadata(),
            "process": self.process_name,
            "process_index": decimal_string(self.process_index),
            "label": self.label,
            "parameters": deepcopy(self.parameters),
            "main_parameters": deepcopy(self.main_parameters),
        }


@dataclass(frozen=True)
class _Segment:
    start: int
    size: int
    steps: tuple[ProcessStep, ...]
    group: RepeatGroup | None = None


class ProtocolPlan:
    """An accepted compact snapshot; all exposed dictionaries are independent."""

    def __init__(
        self,
        *,
        source_document: dict[str, Any],
        document: dict[str, Any],
        resolved_document: dict[str, Any],
        source_schema_version: int,
        segments: tuple[_Segment, ...],
        total_executions: int,
    ) -> None:
        self._source_document = deepcopy(source_document)
        self._document = deepcopy(document)
        self._resolved_document = deepcopy(resolved_document)
        self.source_schema_version = source_schema_version
        self.total_executions = total_executions
        self._segments = segments
        self._segment_starts = tuple(segment.start for segment in segments)

    @property
    def document(self) -> dict[str, Any]:
        return deepcopy(self._document)

    @property
    def source_document(self) -> dict[str, Any]:
        return deepcopy(self._source_document)

    @property
    def resolved_document(self) -> dict[str, Any]:
        return deepcopy(self._resolved_document)

    def summary(self) -> dict[str, Any]:
        return {
            "schema_version": PROTOCOL_SCHEMA_VERSION,
            "planner_version": PLANNER_VERSION,
            "source_schema_version": self.source_schema_version,
            "document": self.document,
            "source_document": self.source_document,
            "resolved_document": self.resolved_document,
            "total_executions": decimal_string(self.total_executions),
        }

    def _occurrence(self, segment: _Segment, relative_index: int) -> ProcessOccurrence:
        body_size = len(segment.steps)
        step = segment.steps[relative_index % body_size]
        execution_index = segment.start + relative_index
        process_index = (
            step.legacy_index if step.legacy_index is not None else execution_index
        )
        group = segment.group
        return ProcessOccurrence(
            execution_key=step.legacy_key
            or f"{step.process}_{decimal_string(execution_index)}",
            process_name=step.process,
            process_index=process_index,
            parameters=deepcopy(step.parameters),
            main_parameters=deepcopy(self._resolved_document["main_parameter"]),
            source_id=step.id,
            group_id=group.id if group else None,
            label=group.label if group else None,
            cycle=relative_index // body_size + 1 if group else None,
            count=group.count if group else None,
            execution_index=execution_index,
        )

    def iter_occurrences(self) -> Iterator[ProcessOccurrence]:
        """Generate fresh settings only as each process occurrence is requested."""
        for segment in self._segments:
            for relative_index in range(segment.size):
                yield self._occurrence(segment, relative_index)

    def preview(self, offset: str | int = "0", limit: int = 20) -> dict[str, Any]:
        if type(offset) is int:
            if offset < 0:
                raise ValueError("offset: must be at least 0.")
            position = offset
        else:
            position = parse_decimal_string(offset, field="offset")
        if type(limit) is not int or not 1 <= limit <= MAX_PREVIEW_LIMIT:
            raise ValueError(
                f"limit: must be an integer from 1 to {MAX_PREVIEW_LIMIT}."
            )
        end = min(position + limit, self.total_executions)
        occurrences = []
        cursor = position
        if cursor < end:
            segment_index = bisect_right(self._segment_starts, cursor) - 1
            while cursor < end:
                segment = self._segments[segment_index]
                segment_end = min(segment.start + segment.size, end)
                while cursor < segment_end:
                    occurrences.append(
                        self._occurrence(segment, cursor - segment.start).to_dict()
                    )
                    cursor += 1
                segment_index += 1
        return {
            "document": self.document,
            "total_executions": decimal_string(self.total_executions),
            "offset": decimal_string(position),
            "limit": limit,
            "next_offset": decimal_string(end) if end < self.total_executions else None,
            "occurrences": occurrences,
        }


def _resolve_parameters(
    model: type[BaseModel], parameters: dict[str, Any], where: str
) -> dict[str, Any]:
    try:
        return model.model_validate(deepcopy(parameters), by_name=True).model_dump(
            mode="json"
        )
    except ValidationError as exc:
        messages = []
        for error in exc.errors(include_url=False, include_input=False):
            field = ".".join(str(part) for part in error["loc"]) or "parameters"
            messages.append(f"{where} / {field}: {error['msg']}")
        raise ValueError("; ".join(messages)) from exc


def build_protocol_plan(
    data: dict[str, Any],
    registry: Mapping[str, type[BaseModel]],
    main_model: type[BaseModel] | None = None,
) -> ProtocolPlan:
    """Validate every source once and resolve defaults before any execution."""
    document = normalize_protocol_document(data)
    main = (
        _resolve_parameters(main_model, document.main_parameter, "main_parameter")
        if main_model is not None
        else deepcopy(document.main_parameter)
    )
    canonical = document.to_dict()
    if "main_parameter" not in data:
        canonical["main_parameter"] = deepcopy(main)

    def resolve(step: ProcessStep, prefix: str = "") -> ProcessStep:
        where = f"{prefix}{step.process} [{step.id}]"
        if step.process not in registry:
            raise ValueError(f"{where} / process: Unknown process '{step.process}'.")
        parameters = _resolve_parameters(registry[step.process], step.parameters, where)
        return ProcessStep(
            step.id, step.process, parameters, step.legacy_key, step.legacy_index
        )

    total = 0
    segments = []
    resolved_items = []
    for item in document.sequence:
        if isinstance(item, ProcessStep):
            step = resolve(item)
            segments.append(_Segment(total, 1, (step,)))
            resolved_items.append(step.to_dict())
            total += 1
        else:
            body = tuple(
                resolve(step, f"{item.label or 'Repeat'} [{item.id}] / ")
                for step in item.steps
            )
            group = RepeatGroup(item.id, item.label, item.count, body)
            size = item.count * len(body)
            segments.append(_Segment(total, size, body, group))
            resolved_items.append(group.to_dict())
            total += size
    return ProtocolPlan(
        source_document=data,
        document=canonical,
        resolved_document={
            "schema_version": PROTOCOL_SCHEMA_VERSION,
            "main_parameter": main,
            "sequence": resolved_items,
        },
        source_schema_version=document.source_schema_version,
        segments=tuple(segments),
        total_executions=total,
    )
