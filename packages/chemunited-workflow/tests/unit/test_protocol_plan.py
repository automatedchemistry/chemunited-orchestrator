"""Shared structure, exact arithmetic, and bounded lazy protocol planning."""

from copy import deepcopy
from itertools import islice

import pytest
from pydantic import BaseModel, Field

from chemunited_workflow.protocol_document import decimal_string
from chemunited_workflow.protocol_plan import build_protocol_plan


class Config(BaseModel):
    amount: int = Field(default=2, ge=0)
    settings: dict = Field(default_factory=lambda: {"labels": []})


class Main(BaseModel):
    title: str = "Default experiment"
    settings: dict = Field(default_factory=lambda: {"labels": []})


REGISTRY = {"prepare": Config, "do_work": Config, "finish": Config}


def process(source_id, name="do_work", **parameters):
    return {
        "type": "process",
        "id": source_id,
        "process": name,
        "parameters": parameters,
    }


def repeat(source_id="assembly", count="3", steps=None, label="Assembly cycle"):
    return {
        "type": "repeat",
        "id": source_id,
        "label": label,
        "count": count,
        "steps": steps if steps is not None else [process("work")],
    }


def document(*sequence, **main):
    return {"schema_version": 2, "main_parameter": main, "sequence": list(sequence)}


def test_example_has_sixteen_occurrences_and_source_cycle_mapping():
    body = [process(f"chemistry-{i}", amount=i) for i in range(4)]
    data = document(
        process("initiation", "prepare"),
        repeat(steps=body),
        process("settling-delay", "finish"),
        process("methanolysis", "finish"),
        process("termination", "finish"),
    )
    plan = build_protocol_plan(data, REGISTRY, Main)
    occurrences = list(plan.iter_occurrences())
    assert plan.total_executions == 16
    assert [item.source_id for item in occurrences] == [
        "initiation",
        *[f"chemistry-{i}" for _ in range(3) for i in range(4)],
        "settling-delay",
        "methanolysis",
        "termination",
    ]
    assert [item.cycle for item in occurrences] == [
        None,
        *([1] * 4),
        *([2] * 4),
        *([3] * 4),
        None,
        None,
        None,
    ]
    assert [item.parameters["amount"] for item in occurrences[1:13]] == [0, 1, 2, 3] * 3
    assert all(
        item.group_id == "assembly" and item.label == "Assembly cycle"
        for item in occurrences[1:13]
    )
    assert len({item.execution_key for item in occurrences}) == 16
    assert [item.execution_index for item in occurrences] == list(range(16))
    assert occurrences[5].execution_key == "do_work_5"
    assert occurrences[5].metadata() == {
        "execution_key": "do_work_5",
        "process_name": "do_work",
        "source_id": "chemistry-0",
        "group_id": "assembly",
        "group_label": "Assembly cycle",
        "cycle": "2",
        "count": "3",
        "execution_index": "5",
    }


def test_sequential_groups_and_repeated_names_have_deterministic_unique_keys():
    data = document(
        process("outside-before"),
        repeat("first", "2", [process("first-step")]),
        process("between"),
        repeat("second", "3", [process("second-step")]),
        process("outside-after"),
    )
    plan = build_protocol_plan(data, REGISTRY)
    occurrences = list(plan.iter_occurrences())
    assert [item.execution_key for item in occurrences] == [
        f"do_work_{i}" for i in range(8)
    ]
    assert [item.group_id for item in occurrences] == [
        None,
        "first",
        "first",
        None,
        "second",
        "second",
        "second",
        None,
    ]
    assert [
        item.execution_key
        for item in build_protocol_plan(data, REGISTRY).iter_occurrences()
    ] == [item.execution_key for item in occurrences]


@pytest.mark.parametrize(
    "count",
    [
        "2",
        "11",
        "1000",
        "9007199254740993",
        "10000000000000000000000000000000000000000",
    ],
)
def test_repeat_counts_have_no_application_ceiling(count):
    plan = build_protocol_plan(document(repeat(count=count)), REGISTRY)
    assert decimal_string(plan.total_executions) == count
    assert plan.document["sequence"][0]["count"] == count
    assert len(list(islice(plan.iter_occurrences(), 2))) == 2


@pytest.mark.parametrize(
    "count",
    [
        "1",
        "0",
        "-2",
        "+2",
        "2.0",
        "2e3",
        "02",
        " 2",
        "2 ",
        "٢",
        "",
        2,
        2.0,
        True,
        False,
        None,
    ],
)
def test_invalid_counts_name_group_and_field(count):
    with pytest.raises(ValueError, match=r"Assembly cycle \[assembly\] / count"):
        build_protocol_plan(document(repeat(count=count)), REGISTRY)


def test_missing_count_is_rejected():
    group = repeat()
    del group["count"]
    with pytest.raises(ValueError, match="assembly.*count"):
        build_protocol_plan(document(group), REGISTRY)


def test_huge_late_preview_uses_arithmetic_without_iterating_earlier_cycles(
    monkeypatch,
):
    count = 10**40 + 7
    plan = build_protocol_plan(
        document(
            process("before", "prepare"),
            repeat(count=decimal_string(count), steps=[process("one"), process("two")]),
            process("after", "finish"),
        ),
        REGISTRY,
    )
    calls = []
    original = plan._occurrence

    def occurrence(segment, relative_index):
        calls.append(relative_index)
        return original(segment, relative_index)

    monkeypatch.setattr(plan, "_occurrence", occurrence)
    monkeypatch.setattr(
        plan,
        "iter_occurrences",
        lambda: pytest.fail("preview must seek, not enumerate"),
    )
    offset = 2 * count - 1
    page = plan.preview(decimal_string(offset), 3)
    assert len(calls) == 3
    assert page["offset"] == decimal_string(offset)
    assert page["total_executions"] == decimal_string(2 * count + 2)
    assert page["next_offset"] is None
    assert [item["source_id"] for item in page["occurrences"]] == [
        "one",
        "two",
        "after",
    ]
    assert [item["cycle"] for item in page["occurrences"]] == [
        decimal_string(count),
        decimal_string(count),
        None,
    ]
    assert [item["execution_index"] for item in page["occurrences"]] == [
        decimal_string(offset + i) for i in range(3)
    ]
    assert page["occurrences"][0]["process_index"] == decimal_string(offset)


def test_count_and_offset_beyond_python_default_decimal_digit_limit():
    count_text = "1" + "0" * 4500
    plan = build_protocol_plan(document(repeat(count=count_text)), REGISTRY)
    last_index = plan.total_executions - 1
    page = plan.preview(decimal_string(last_index), 1)
    assert page["total_executions"] == count_text
    assert page["occurrences"][0]["cycle"] == count_text
    assert page["occurrences"][0]["execution_key"] == "do_work_" + decimal_string(
        last_index
    )


@pytest.mark.parametrize(
    "offset", ["-1", "01", "+1", "1.0", "1e3", "١", True, None, -1]
)
def test_preview_rejects_inexact_or_invalid_offsets(offset):
    with pytest.raises(ValueError, match="offset"):
        build_protocol_plan(document(repeat()), REGISTRY).preview(offset)


@pytest.mark.parametrize("limit", [0, 201, -1, 2.5, True, "2"])
def test_preview_is_bounded(limit):
    with pytest.raises(ValueError, match="limit"):
        build_protocol_plan(document(repeat()), REGISTRY).preview(limit=limit)


def test_preview_pages_and_offsets_after_end():
    plan = build_protocol_plan(document(repeat(count="11")), REGISTRY)
    assert plan.preview("0", 2)["next_offset"] == "2"
    assert plan.preview("10", 2)["next_offset"] is None
    page = plan.preview("9007199254740993", 2)
    assert page["offset"] == "9007199254740993"
    assert page["occurrences"] == []
    assert page["next_offset"] is None


def test_legacy_preserves_insertion_order_keys_suffixes_and_process_names():
    data = {
        "do_work_9": {"amount": 9},
        "main_parameter": {"title": "Legacy"},
        "prepare_3": {},
        "do_work_02": {"amount": 2},
    }
    plan = build_protocol_plan(data, REGISTRY, Main)
    occurrences = list(plan.iter_occurrences())
    assert [
        (item.execution_key, item.process_index, item.source_id) for item in occurrences
    ] == [
        ("do_work_9", 9, "do_work_9"),
        ("prepare_3", 3, "prepare_3"),
        ("do_work_02", 2, "do_work_02"),
    ]
    assert [item.execution_index for item in occurrences] == [0, 1, 2]
    assert [item["id"] for item in plan.document["sequence"]] == [
        "do_work_9",
        "prepare_3",
        "do_work_02",
    ]
    assert plan.source_document == data
    assert plan.summary()["source_schema_version"] == 1
    assert plan.preview()["occurrences"][2]["execution_key"] == "do_work_02"


def test_plan_freezes_input_documents_and_isolates_every_occurrence():
    data = document(
        repeat(steps=[process("work", settings={"labels": ["shared"]})]),
        settings={"labels": ["main"]},
    )
    original = deepcopy(data)
    plan = build_protocol_plan(data, REGISTRY, Main)
    first, second = list(islice(plan.iter_occurrences(), 2))
    first.parameters["settings"]["labels"].append("changed")
    first.main_parameters["settings"]["labels"].append("changed")
    assert second.parameters["settings"]["labels"] == ["shared"]
    assert second.main_parameters["settings"]["labels"] == ["main"]
    data["sequence"][0]["steps"][0]["parameters"]["amount"] = 99
    plan.document["sequence"].clear()
    plan.resolved_document["sequence"].clear()
    plan.source_document.clear()
    assert plan.source_document == original
    assert next(plan.iter_occurrences()).parameters["amount"] == 2
    assert plan.preview()["occurrences"][0]["parameters"]["settings"]["labels"] == [
        "shared"
    ]


def test_defaults_are_resolved_once_per_source_not_per_cycle():
    calls = []

    class Counted(BaseModel):
        value: int = Field(default_factory=lambda: calls.append("process") or 7)

    class CountedMain(BaseModel):
        value: int = Field(default_factory=lambda: calls.append("main") or 8)

    plan = build_protocol_plan(
        document(repeat(count="1000")), {"do_work": Counted}, CountedMain
    )
    assert calls == ["main", "process"]
    assert plan.document["sequence"][0]["steps"][0]["parameters"] == {}
    assert plan.resolved_document["sequence"][0]["steps"][0]["parameters"] == {
        "value": 7
    }
    assert all(
        item.parameters == {"value": 7} for item in islice(plan.iter_occurrences(), 20)
    )
    assert plan.preview("999", 1)["occurrences"][0]["main_parameters"] == {"value": 8}
    assert calls == ["main", "process"]


def test_resolved_snapshots_preserve_validation_alias_values_when_replanned():
    class Aliased(BaseModel):
        rate: int = Field(default=2, validation_alias="FLOW")

    class AliasedMain(BaseModel):
        amount: int = Field(default=3, validation_alias="AMOUNT")

    plan = build_protocol_plan(
        document(repeat(steps=[process("work", FLOW=9)]), AMOUNT=11),
        {"do_work": Aliased},
        AliasedMain,
    )
    assert next(plan.iter_occurrences()).parameters == {"rate": 9}
    assert next(plan.iter_occurrences()).main_parameters == {"amount": 11}
    replanned = build_protocol_plan(
        plan.resolved_document, {"do_work": Aliased}, AliasedMain
    )
    assert next(replanned.iter_occurrences()).parameters == {"rate": 9}
    assert next(replanned.iter_occurrences()).main_parameters == {"amount": 11}


@pytest.mark.parametrize(
    "data,message",
    [
        ({"schema_version": 3, "sequence": []}, "schema_version"),
        ({"schema_version": True, "sequence": []}, "schema_version"),
        ({"schema_version": "2", "sequence": []}, "schema_version"),
        ({"schema_version": 2}, "sequence"),
        ({"schema_version": 2, "sequence": [], "extra": {}}, "unsupported field"),
        (document({"type": "other", "id": "bad"}), "bad.*type"),
        (document(process("same"), process("same")), "duplicate source ID 'same'"),
        (
            document(repeat("same", steps=[process("same")])),
            "duplicate source ID 'same'",
        ),
        (document(repeat(steps=[])), "assembly.*steps"),
        (document(repeat(steps=[repeat("nested")])), "assembly.*nested repeat"),
        (document(process("", "prepare")), "id"),
        (document(process("missing", "unknown")), "unknown.*missing.*process"),
        (
            document(repeat(steps=[process("bad-settings", amount=-1)])),
            "Assembly cycle.*do_work.*bad-settings.*amount",
        ),
        (document(process("main-check"), title=[]), "main_parameter.*title"),
        ({"not-a-key": {}}, "not-a-key"),
        ({"do_work_0": []}, "do_work_0.*parameters"),
        (
            document(
                {"type": "process", "id": "x", "process": "do_work", "parameters": []}
            ),
            "x.*parameters",
        ),
        (document(process("one"), **{"settings": []}), "main_parameter.*settings"),
    ],
)
def test_invalid_source_errors_identify_item_and_field(data, message):
    with pytest.raises(ValueError, match=message):
        build_protocol_plan(data, REGISTRY, Main)


def test_empty_legacy_or_v2_sequences_are_valid_compact_documents():
    for data in ({}, document()):
        plan = build_protocol_plan(data, REGISTRY, Main)
        assert plan.total_executions == 0
        assert plan.preview()["occurrences"] == []
        assert list(plan.iter_occurrences()) == []
        assert plan.summary()["planner_version"] == 1
        assert plan.document["schema_version"] == 2
