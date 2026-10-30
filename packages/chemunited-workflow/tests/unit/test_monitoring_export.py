"""Unit tests for monitoring recordings as tables: one SQLite database for
any number of runs and a CSV per run, built from the runs' JSONL."""

from __future__ import annotations

import contextlib
import csv
import io
import json
import sqlite3
import zipfile

import pytest
from loguru import logger

from chemunited_workflow.api.monitoring_store import MonitoringStore
from chemunited_workflow.api.run_manifest import manifest_path, write_run_manifest
from chemunited_workflow.api.services.monitoring import MonitoringService
from chemunited_workflow.api.services.monitoring_export import (
    CSV_COLUMNS,
    add_monitoring_tables,
    build_database,
    typed_value,
    write_run_csv,
)

RUN_ID = "proto_2026-01-01T00-00-00_2026-01-02T10-00-00"
OLD_RUN_ID = "proto_2026-01-01T00-00-00_2025-12-01T09-00-00"
CONFIG = {
    "sample_time": 0.5,
    "request_timeout": 2.0,
    "variables": [
        {"component": "custom", "command": "mixed", "kwargs": {}},
        {"component": "adc", "command": "read", "kwargs": {"channel": 2}},
    ],
}
MIXED = [
    {"tick": 0, "time": "t0", "value": 24.5, "error": None, "unit": "°C"},
    {"tick": 1, "time": "t1", "value": True, "error": None},
    {"tick": 2, "time": "t2", "value": "open", "error": None},
    {"tick": 3, "time": "t3", "value": [1, 2.5], "error": None},
    {"tick": 4, "time": "t4", "value": {"a": 1}, "error": None},
    {"tick": 5, "time": "t5", "value": None, "error": "offline"},
]
CHANNEL = [
    {"tick": 0, "time": "t0", "value": 3, "error": None},
    {"tick": 1, "time": "t1", "value": 4, "error": None},
]


def _write(path, readings, tail: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = "".join(json.dumps(reading) + "\n" for reading in readings)
    path.write_text(lines + tail, encoding="utf-8")


@pytest.fixture
def project(tmp_path):
    """One run recorded with recording.json, one from before it existed."""
    run_dir = tmp_path / "log" / "monitoring" / RUN_ID
    _write(run_dir / "custom__mixed.jsonl", MIXED)
    _write(run_dir / "adc__read__channel=2.jsonl", CHANNEL)
    service = MonitoringService(project_dir=tmp_path, store=MonitoringStore())
    service._describe_recording(run_dir, CONFIG)

    old_dir = tmp_path / "log" / "monitoring" / OLD_RUN_ID
    _write(
        old_dir / "Disposal__injection-valve__position.jsonl",
        [{"tick": 0, "time": "t0", "value": "1-2", "error": None}],
    )
    _write(
        old_dir / "adc__read__channel=2.jsonl",
        [{"tick": 0, "time": "t0", "value": 3, "error": None}],
    )
    return tmp_path


@contextlib.contextmanager
def _database(project_dir, run_ids):
    path = project_dir / "out.db"
    build_database(project_dir, run_ids, path)
    with contextlib.closing(sqlite3.connect(path)) as conn:
        yield conn


@pytest.fixture
def warnings_log():
    captured: list[str] = []
    sink_id = logger.add(lambda message: captured.append(str(message)), level="WARNING")
    yield captured
    logger.remove(sink_id)


# ── typed_value ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("value", "stored", "value_type"),
    [
        (None, None, "null"),
        (True, 1, "boolean"),
        (False, 0, "boolean"),
        (3, 3, "number"),
        (2.5, 2.5, "number"),
        (2**70, str(2**70), "number"),
        ("open", "open", "string"),
        ([1, "a"], '[1, "a"]', "array"),
        ({"a": "°C"}, '{"a": "°C"}', "object"),
    ],
)
def test_typed_value(value, stored, value_type):
    assert typed_value(value) == (stored, value_type)


# ── build_database ───────────────────────────────────────────────────────────


def test_each_reading_keeps_its_own_type(project):
    with _database(project, [RUN_ID]) as conn:
        rows = conn.execute(
            "SELECT value_type, typeof(value), unit, error FROM readings_long"
            " WHERE variable = 'custom::mixed' ORDER BY tick"
        ).fetchall()
        second = conn.execute(
            "SELECT json_extract(value, '$[1]') FROM readings_long"
            " WHERE value_type = 'array'"
        ).fetchone()

    assert rows == [
        ("number", "real", "°C", None),
        ("boolean", "integer", None, None),
        ("string", "text", None, None),
        ("array", "text", None, None),
        ("object", "text", None, None),
        ("null", "null", None, "offline"),
    ]
    assert second == (2.5,)


def test_variables_come_from_the_recording_description(project):
    with _database(project, [RUN_ID]) as conn:
        rows = conn.execute(
            "SELECT key, component, command, params, file FROM variables ORDER BY file"
        ).fetchall()

    assert rows == [
        (
            'adc::read::{"channel":2}',
            "adc",
            "read",
            '{"channel":2}',
            "adc__read__channel=2.jsonl",
        ),
        ("custom::mixed", "custom", "mixed", None, "custom__mixed.jsonl"),
    ]


def test_an_older_recording_is_read_back_from_its_file_names(project):
    with _database(project, [OLD_RUN_ID]) as conn:
        variables = conn.execute(
            "SELECT key, component, command, params FROM variables ORDER BY file"
        ).fetchall()
        run = conn.execute("SELECT sample_time, protocol FROM runs").fetchone()

    assert variables == [
        # The same key a recording with recording.json gets.
        (
            "Disposal::injection-valve/position",
            "Disposal",
            "injection-valve/position",
            None,
        ),
        # Parameters made file-safe can't be read back: the file name stays.
        ("adc__read__channel=2", "adc", "read", None),
    ]
    assert run == (None, None)


def test_a_run_row_comes_from_its_manifest_and_recording(project):
    manifest = {
        "run_id": RUN_ID,
        "state": "cancelled",
        "reason": "Overpressure",
        "started_at": "2026-01-02T10:00:00+01:00",
        "finished_at": "2026-01-02T10:05:00+01:00",
        "protocol": {"filename": "proto_2026-01-01T00-00-00.json", "content": {}},
        "project": {"name": "demo", "git": {"commit": "a1b2c3d4", "dirty": True}},
    }
    write_run_manifest(manifest_path(project, RUN_ID), manifest)

    with _database(project, [RUN_ID]) as conn:
        row = conn.execute(
            "SELECT protocol, state, reason, started_at, finished_at, git_commit,"
            " git_dirty, sample_time, request_timeout, manifest FROM runs"
        ).fetchone()
        version = conn.execute("PRAGMA user_version").fetchone()

    assert row[:-1] == (
        "proto_2026-01-01T00-00-00.json",
        "cancelled",
        "Overpressure",
        "2026-01-02T10:00:00+01:00",
        "2026-01-02T10:05:00+01:00",
        "a1b2c3d4",
        1,
        0.5,
        2.0,
    )
    assert json.loads(row[-1]) == manifest
    assert version == (1,)


def test_a_line_that_is_not_a_reading_is_skipped(project, warnings_log):
    channel = project / "log" / "monitoring" / RUN_ID / "adc__read__channel=2.jsonl"
    _write(channel, CHANNEL, tail='{"tick": 2, "val')  # still being written

    with _database(project, [RUN_ID]) as conn:
        ticks = conn.execute(
            "SELECT tick FROM readings_long WHERE command = 'read' ORDER BY tick"
        ).fetchall()

    assert ticks == [(0,), (1,)]
    assert any("Skipped 1 unreadable line" in message for message in warnings_log)


# ── write_run_csv ────────────────────────────────────────────────────────────


def test_the_csv_has_one_row_per_reading_by_tick_then_variable(project):
    stream = io.StringIO()
    with _database(project, [RUN_ID]) as conn:
        count = write_run_csv(conn, RUN_ID, stream)

    rows = list(csv.reader(io.StringIO(stream.getvalue())))
    assert tuple(rows[0]) == CSV_COLUMNS
    assert count == len(rows) - 1 == 8
    cells = [(row[5], row[1], row[7], row[8]) for row in rows[1:]]
    assert cells == [
        ("0", 'adc::read::{"channel":2}', "3", "number"),
        ("0", "custom::mixed", "24.5", "number"),
        ("1", 'adc::read::{"channel":2}', "4", "number"),
        ("1", "custom::mixed", "true", "boolean"),
        ("2", "custom::mixed", "open", "string"),
        ("3", "custom::mixed", "[1, 2.5]", "array"),
        ("4", "custom::mixed", '{"a": 1}', "object"),
        ("5", "custom::mixed", "", "null"),
    ]
    first = dict(zip(CSV_COLUMNS, rows[2]))
    assert (first["run_id"], first["component"], first["unit"]) == (
        RUN_ID,
        "custom",
        "°C",
    )
    assert dict(zip(CSV_COLUMNS, rows[-1]))["error"] == "offline"


# ── add_monitoring_tables ────────────────────────────────────────────────────


def test_tables_go_in_the_zip(project, tmp_path):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as zf:
        names = add_monitoring_tables(zf, project, [RUN_ID, OLD_RUN_ID, "unrecorded"])

    assert names == {
        "database": "monitoring.db",
        "csv": {
            RUN_ID: f"monitoring/{RUN_ID}.csv",
            OLD_RUN_ID: f"monitoring/{OLD_RUN_ID}.csv",
        },
    }
    with zipfile.ZipFile(buffer) as zf:
        content = zf.read(f"monitoring/{RUN_ID}.csv")
        (tmp_path / "copy.db").write_bytes(zf.read("monitoring.db"))
    # A BOM, so spreadsheets read "°C" as UTF-8.
    assert content.startswith(b"\xef\xbb\xbf")
    assert "°C" in content.decode("utf-8-sig")
    with contextlib.closing(sqlite3.connect(tmp_path / "copy.db")) as conn:
        runs = conn.execute("SELECT run_id FROM runs ORDER BY run_id").fetchall()
    assert runs == [(OLD_RUN_ID,), (RUN_ID,)]


def test_no_recording_no_tables(tmp_path):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as zf:
        names = add_monitoring_tables(zf, tmp_path, ["unrecorded"])
    assert names == {"database": None, "csv": {}}
    with zipfile.ZipFile(buffer) as zf:
        assert zf.namelist() == []
