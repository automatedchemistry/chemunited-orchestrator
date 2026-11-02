from __future__ import annotations

import json
from pathlib import Path

from pytestqt.qtbot import QtBot

from chemunited.simulation import pool_log_tailer
from chemunited.simulation.pool_log_tailer import PoolLogTailer


def _append(pool_dir: Path, component: str, *entries: dict) -> None:
    pool_dir.mkdir(parents=True, exist_ok=True)
    with (pool_dir / f"{component}.jsonl").open("a", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(entry) + "\n")


def test_first_tick_discards_leftovers_then_ticks_apply_new_commands(
    qtbot: QtBot, monkeypatch, tmp_path
):
    applied: list[dict] = []
    monkeypatch.setattr(
        pool_log_tailer,
        "apply_pool_command",
        lambda components, entry: applied.append(entry),
    )
    pool_dir = tmp_path / "log" / "pool"
    _append(pool_dir, "PumpA", {"component": "PumpA", "command": "stale"})
    tailer = PoolLogTailer(tmp_path, components={})  # type: ignore[arg-type]

    tailer._tick()

    assert applied == []
    assert list(pool_dir.iterdir()) == []

    _append(
        pool_dir,
        "PumpA",
        {"component": "PumpA", "command": "infuse"},
        {"component": "PumpA", "command": "stop"},
    )
    tailer._tick()

    assert [entry["command"] for entry in applied] == ["infuse", "stop"]
    assert list(pool_dir.iterdir()) == []
