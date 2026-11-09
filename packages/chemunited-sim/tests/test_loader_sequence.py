"""A protocol's steps run in key order, as on the instrument."""

from __future__ import annotations

import json

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
