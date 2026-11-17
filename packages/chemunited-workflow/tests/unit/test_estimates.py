"""Duration estimates: parsing, per-step evaluation and exact protocol totals."""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

import networkx as nx
import pytest
from pydantic import BaseModel, Field

from chemunited_quantities import ChemQuantityValidator, ChemUnitQuantity
from chemunited_workflow import Process
from chemunited_workflow.durations import parse_duration
from chemunited_workflow.estimates import estimate_plan
from chemunited_workflow.protocol_plan import build_protocol_plan

# ── parse_duration ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("value", "seconds"),
    [
        ("15 min", 900.0),
        ("1.5 h", 5400.0),
        ("  90 s ", 90.0),
        (30, 30.0),
        (2.5, 2.5),
        (0, 0.0),
        (timedelta(minutes=2), 120.0),
        (ChemUnitQuantity("3 min"), 180.0),
        (ChemUnitQuantity("10 ml") / ChemUnitQuantity("2 ml / min"), 300.0),
    ],
)
def test_parse_duration_accepts_times_numbers_quantities_and_timedeltas(value, seconds):
    assert parse_duration(value) == pytest.approx(seconds)


@pytest.mark.parametrize("value", [None, "", "   "])
def test_parse_duration_treats_empty_values_as_no_estimate(value):
    assert parse_duration(value) is None


@pytest.mark.parametrize(
    "value",
    [
        "90",  # no unit: seconds or minutes?
        True,
        -1,
        "-5 s",
        float("inf"),
        float("nan"),
        "5 ml",
        "not a unit",
        ChemUnitQuantity("2 ml"),
        timedelta(seconds=-1),
        object(),
        [1],
    ],
)
def test_parse_duration_rejects_values_that_are_not_a_non_negative_time(value):
    with pytest.raises(ValueError, match="duration estimate"):
        parse_duration(value)


# ── estimate_plan ──────────────────────────────────────────────────────────────


class Plain(BaseModel):
    pass


class Flow(BaseModel):
    volume: Annotated[ChemUnitQuantity, ChemQuantityValidator("ml")] = Field(
        default=ChemUnitQuantity("10 ml")
    )
    flow_rate: Annotated[ChemUnitQuantity, ChemQuantityValidator("ml / min")] = Field(
        default=ChemUnitQuantity("1 ml / min")
    )


class Main(BaseModel):
    minutes_per_step: float = 2.0


class _Base(Process[BaseModel]):
    def build_workflow(self) -> nx.DiGraph:
        return nx.DiGraph()


class Fixed(_Base):
    estimated_duration = "15 min"


class FlowTime(_Base):
    def estimate_duration(self):
        return self.config.volume / self.config.flow_rate


class FromMain(_Base):
    def estimate_duration(self):
        return self.main_parameters.minutes_per_step * 60


class Unestimated(_Base):
    pass


class Broken(_Base):
    def estimate_duration(self):
        return self.config.volume / (self.config.flow_rate * 0)


class TouchesDevices(_Base):
    def estimate_duration(self):
        return self.platform["pump"].get("rate")


class Unitless(_Base):
    estimated_duration = "90"


class NotAProcess:
    """Registry stand-in, as some integrations and tests use."""

    estimated_duration = "2 min"


PROCESSES = {
    "fixed": Fixed,
    "flow": FlowTime,
    "from_main": FromMain,
    "plain": Unestimated,
    "broken": Broken,
    "devices": TouchesDevices,
    "unitless": Unitless,
    "legacy": NotAProcess,
}
CONFIGS = {
    "fixed": Plain,
    "flow": Flow,
    "from_main": Plain,
    "plain": Plain,
    "broken": Flow,
    "devices": Plain,
    "unitless": Plain,
    "legacy": Plain,
}


def process(source_id, name, **parameters):
    return {
        "type": "process",
        "id": source_id,
        "process": name,
        "parameters": parameters,
    }


def document(count="3", *steps):
    return {
        "schema_version": 2,
        "main_parameter": {"minutes_per_step": 4},
        "sequence": [
            process("fixed", "fixed"),
            {
                "type": "repeat",
                "id": "cycle",
                "label": "Cycle",
                "count": count,
                "steps": [
                    process("flow", "flow", volume="10 ml", flow_rate="2 ml / min"),
                    process("plain", "plain"),
                ],
            },
            process("from_main", "from_main"),
            *steps,
        ],
    }


def estimate(data):
    plan = build_protocol_plan(data, CONFIGS, Main)
    return estimate_plan(plan, PROCESSES, CONFIGS, Main)


def test_fixed_formula_and_main_parameter_estimates_add_up_per_execution():
    result = estimate(document("3"))
    assert result == {
        "step_ms": {
            "fixed": "900000",  # 15 min
            "flow": "300000",  # 10 ml at 2 ml/min
            "plain": None,
            "from_main": "240000",  # 4 min from the main parameters
        },
        "total_ms": str(900000 + 3 * 300000 + 240000),
        "unestimated_executions": "3",
        "errors": {},
    }


def test_resolved_defaults_feed_the_formula():
    data = document("2")
    data["sequence"][1]["steps"][0]["parameters"] = {}
    assert estimate(data)["step_ms"]["flow"] == "600000"  # 10 ml at 1 ml/min


def test_huge_repeat_counts_stay_exact():
    count = "9007199254740993123456789"
    result = estimate(document(count))
    assert result["total_ms"] == str(900000 + int(count) * 300000 + 240000)
    assert result["unestimated_executions"] == count


def test_failing_estimates_leave_their_step_unestimated_with_a_reason():
    data = document(
        "2",
        process("broken", "broken"),
        process("devices", "devices"),
        process("unitless", "unitless"),
    )
    result = estimate(data)
    assert result["step_ms"]["broken"] is None
    assert result["step_ms"]["devices"] is None
    assert result["step_ms"]["unitless"] is None
    assert result["errors"]["broken"].startswith("ZeroDivisionError")
    assert result["errors"]["devices"].startswith("KeyError")
    assert result["errors"]["unitless"].startswith("ValueError")
    assert result["unestimated_executions"] == "5"  # 2 cycles of plain + 3
    assert result["total_ms"] == str(900000 + 2 * 300000 + 240000)


def test_unregistered_and_non_process_entries():
    data = {
        "schema_version": 2,
        "main_parameter": {},
        "sequence": [process("old", "legacy"), process("gone", "plain")],
    }
    plan = build_protocol_plan(data, CONFIGS, Main)
    result = estimate_plan(plan, {"legacy": NotAProcess}, CONFIGS, Main)
    assert result["step_ms"] == {"old": "120000", "gone": None}
    assert result["errors"] == {}
    assert result["unestimated_executions"] == "1"


def test_base_process_has_no_estimate_by_default():
    assert Process.estimated_duration is None
    assert Unestimated(config=Plain()).estimate_duration() is None
    assert Fixed(config=Plain()).estimate_duration() == "15 min"
