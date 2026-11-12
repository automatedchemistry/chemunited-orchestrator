"""A protocol's steps run in key order, as on the instrument."""

from __future__ import annotations

import json

import pytest

from chemunited_sim.cli.loader import parse_historical_file
from chemunited_workflow.api.services.runner import RunnerService


def test_sequence_is_in_key_order_like_the_real_runner(tmp_path) -> None:
    data = {
        "main_parameter": {},
        "Work_5": {"seconds": 1.0},
        "Boom_2": {},
        "Work_0": {},
        "not a step": {},
    }
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    _, sequence = parse_historical_file(path)

    assert [(step.process, step.index) for step in sequence] == [
        ("Work", 5),
        ("Boom", 2),
        ("Work", 0),
    ]
    assert sequence[0].params == {"seconds": 1.0}
    assert sequence[0].key == "Work_5"
    assert [
        (step.process, step.index) for step in sequence
    ] == RunnerService._parse_sequence(data)


def test_versioned_protocol_is_explicitly_rejected_before_empty_execution(tmp_path):
    path = tmp_path / "repeat.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "sequence": [
                    {
                        "type": "repeat",
                        "id": "r",
                        "count": "3",
                        "steps": [
                            {
                                "type": "process",
                                "id": "s",
                                "process": "Work",
                                "parameters": {},
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="does not support versioned/repeat"):
        parse_historical_file(path)
