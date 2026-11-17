"""Advisory duration estimates for a planned protocol.

A process can say how long one execution takes, either fixed
(``Process.estimated_duration``) or worked out from the step's parameters
(``Process.estimate_duration()``). This module evaluates that once per source
step and multiplies by repeat counts instead of iterating occurrences, so the
totals stay exact for counts far beyond 2**53. Durations are whole
milliseconds, serialized as decimal strings like every other unbounded count.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from loguru import logger
from pydantic import BaseModel

from .durations import parse_duration
from .process import Process
from .protocol_document import decimal_string, parse_decimal_string
from .protocol_plan import ProtocolPlan


def estimate_plan(
    plan: ProtocolPlan,
    processes: Mapping[str, type],
    configs: Mapping[str, type[BaseModel]],
    main_parameter_class: type[BaseModel] | None = None,
) -> dict[str, Any]:
    """Return per-step estimates and exact protocol totals, in milliseconds.

    ``step_ms`` maps each source step ID to its estimate for one execution,
    or ``None`` when its process gives none or the estimate failed; the
    reason for a failure is in ``errors``. ``total_ms`` adds up every
    estimated execution, and ``unestimated_executions`` counts the others.
    Never raises because of process code: a broken estimate only leaves its
    step unestimated.
    """
    resolved = plan.resolved_document
    main_values = resolved.get("main_parameter", {})
    step_ms: dict[str, str | None] = {}
    errors: dict[str, str] = {}
    total = 0
    unestimated = 0

    def add(step: dict[str, Any], executions: int) -> None:
        nonlocal total, unestimated
        try:
            milliseconds = _step_milliseconds(
                step, processes, configs, main_parameter_class, main_values
            )
        except Exception as exc:
            # Debug, not warning: the protocol editor asks again on every edit.
            logger.debug(
                "Could not estimate the duration of {} [{}]: {}",
                step["process"],
                step["id"],
                exc,
            )
            errors[step["id"]] = f"{type(exc).__name__}: {exc}"
            milliseconds = None
        if milliseconds is None:
            step_ms[step["id"]] = None
            unestimated += executions
        else:
            step_ms[step["id"]] = decimal_string(milliseconds)
            total += milliseconds * executions

    for item in resolved["sequence"]:
        if item["type"] == "repeat":
            count = parse_decimal_string(
                item["count"], field=f"{item['id']} / count", minimum=2
            )
            for step in item["steps"]:
                add(step, count)
        else:
            add(item, 1)

    return {
        "step_ms": step_ms,
        "total_ms": decimal_string(total),
        "unestimated_executions": decimal_string(unestimated),
        "errors": errors,
    }


def _step_milliseconds(
    step: dict[str, Any],
    processes: Mapping[str, type],
    configs: Mapping[str, type[BaseModel]],
    main_parameter_class: type[BaseModel] | None,
    main_values: dict[str, Any],
) -> int | None:
    """One execution of ``step``, in whole milliseconds, or ``None``."""
    name = step["process"]
    process_class = processes.get(name)
    if process_class is None:
        return None
    if issubclass(process_class, Process):
        config_class = configs.get(name)
        if config_class is None:
            return None
        # The same validated inputs the runner hands the process.
        process = process_class(
            config=config_class.model_validate(step["parameters"], by_name=True)
        )
        if main_parameter_class is not None:
            process.main_parameters = main_parameter_class.model_validate(
                main_values, by_name=True
            )
        value = process.estimate_duration()
    else:
        value = getattr(process_class, "estimated_duration", None)
    seconds = parse_duration(value)
    return None if seconds is None else round(seconds * 1000)
