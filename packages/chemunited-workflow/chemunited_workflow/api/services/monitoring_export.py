"""Monitoring recordings as tables, built at export time from the runs' JSONL.

``build_database`` writes the readings of any number of runs to one SQLite
database, and ``write_run_csv`` writes one run's readings from it as CSV, one
row per reading whatever its value. ``add_monitoring_tables`` puts both in an
export zip; a project's ``customizations/export/export_hook.py`` can use them
too. The JSONL files stay the record: these are only other views of them.

Values keep their type. ``value`` has no declared type in the database, so
each row holds a number, text or NULL as it was read, and ``value_type`` names
its JSON type: ``number``, ``boolean`` (stored 0/1), ``string``, ``array`` and
``object`` (stored as JSON text, for ``json_extract``), or ``null``.

Which variable a file holds comes from the run's ``recording.json``. A
recording from before it existed is read back from its file names, as well as
they allow: their parameters can't be.
"""

from __future__ import annotations

import contextlib
import csv
import io
import json
import sqlite3
import tempfile
import zipfile
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any, TextIO

from loguru import logger

from ..run_manifest import manifest_path, read_run_manifest
from .monitoring import RECORDING_DESCRIPTION, canonical_kwargs, monitoring_key

DATABASE_NAME = "monitoring.db"
DATABASE_VERSION = 1
CSV_DIR = "monitoring"
CSV_COLUMNS = (
    "run_id",
    "variable",
    "component",
    "command",
    "params",
    "tick",
    "time",
    "value",
    "value_type",
    "unit",
    "error",
)

_SCHEMA = """
CREATE TABLE runs (
    run_id TEXT PRIMARY KEY,
    protocol TEXT,
    state TEXT,
    reason TEXT,
    started_at TEXT,
    finished_at TEXT,
    git_commit TEXT,
    git_dirty INTEGER,
    sample_time REAL,
    request_timeout REAL,
    manifest TEXT
);
CREATE TABLE variables (
    id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs (run_id),
    key TEXT NOT NULL,
    component TEXT,
    command TEXT,
    params TEXT,
    file TEXT NOT NULL
);
CREATE TABLE readings (
    variable_id INTEGER NOT NULL REFERENCES variables (id),
    tick INTEGER,
    time TEXT,
    value,
    value_type TEXT NOT NULL,
    unit TEXT,
    error TEXT
);
CREATE INDEX readings_by_variable ON readings (variable_id, tick);
CREATE VIEW readings_long AS
SELECT v.run_id, v.key AS variable, v.component, v.command, v.params,
       r.tick, r.time, r.value, r.value_type, r.unit, r.error
FROM readings AS r JOIN variables AS v ON v.id = r.variable_id;
"""

_INT64 = range(-(2**63), 2**63)


def typed_value(value: Any) -> tuple[Any, str]:
    """A value read from JSON as SQLite stores it, and its JSON type."""
    if value is None:
        return None, "null"
    if isinstance(value, bool):
        return int(value), "boolean"
    if isinstance(value, int):
        # Past SQLite's 64-bit integers: kept whole, as text.
        return (value if value in _INT64 else str(value)), "number"
    if isinstance(value, float):
        return value, "number"
    if isinstance(value, str):
        return value, "string"
    value_type = "array" if isinstance(value, list) else "object"
    return json.dumps(value, ensure_ascii=False), value_type


def _text(value: Any) -> str | None:
    return None if value is None else str(value)


def _number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    return None


def _monitoring_dir(project_dir: Path, run_id: str) -> Path:
    return project_dir / "log" / "monitoring" / run_id


def _description(run_dir: Path) -> dict[str, Any]:
    """The run's ``recording.json``; {} for a recording from before it existed."""
    path = run_dir / RECORDING_DESCRIPTION
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning(
            "Could not read {} of run '{}': {}", path.name, run_dir.name, exc
        )
        return {}
    return data if isinstance(data, dict) else {}


def _variable(
    file: Path, described: dict[str, dict[str, Any]]
) -> tuple[str, str | None, str | None, str | None]:
    """``(key, component, command, params)`` of the variable *file* holds."""
    var = described.get(file.name)
    if var is not None:
        component, command = str(var["component"]), str(var["command"])
        kwargs = var.get("kwargs") if isinstance(var.get("kwargs"), dict) else None
        key = monitoring_key(component, command, kwargs)
        return key, component, command, canonical_kwargs(kwargs) or None
    # Read back from the name: "{component}__{command, '/' as '__'}", then
    # "__{parameters}" for a variable with some: made file-safe, those can't
    # be, so such a variable keeps its file name as its key.
    component, _, rest = file.stem.partition("__")
    head, _, last = rest.rpartition("__")
    if head and "=" in last:
        return file.stem, component, head.replace("__", "/"), None
    command = rest.replace("__", "/")
    if not component or not command:
        return file.stem, component or None, command or None, None
    return monitoring_key(component, command), component, command, None


def _readings(path: Path) -> Iterator[dict[str, Any]]:
    """The readings in one recorded file. A line that isn't one is skipped,
    with a warning: the last line of a recording still going on may be
    half-written."""
    skipped = 0
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                reading = json.loads(line)
            except ValueError:
                reading = None
            if isinstance(reading, dict):
                yield reading
            else:
                skipped += 1
    if skipped:
        logger.warning(
            "Skipped {} unreadable line(s) in {} of run '{}'",
            skipped,
            path.name,
            path.parent.name,
        )


def _run_row(project_dir: Path, run_id: str, description: dict[str, Any]) -> tuple:
    manifest = read_run_manifest(manifest_path(project_dir, run_id)) or {}
    protocol = manifest.get("protocol")
    project = manifest.get("project")
    git = project.get("git") if isinstance(project, dict) else None
    git = git if isinstance(git, dict) else {}
    dirty = git.get("dirty")
    return (
        run_id,
        _text(protocol.get("filename")) if isinstance(protocol, dict) else None,
        _text(manifest.get("state")),
        _text(manifest.get("reason")),
        _text(manifest.get("started_at")),
        _text(manifest.get("finished_at")),
        _text(git.get("commit")),
        None if dirty is None else int(bool(dirty)),
        _number(description.get("sample_time")),
        _number(description.get("request_timeout")),
        json.dumps(manifest, ensure_ascii=False) if manifest else None,
    )


def _reading_row(variable_id: int | None, reading: dict[str, Any]) -> tuple:
    value, value_type = typed_value(reading.get("value"))
    tick = reading.get("tick")
    return (
        variable_id,
        tick if isinstance(tick, int) and not isinstance(tick, bool) else None,
        _text(reading.get("time")),
        value,
        value_type,
        _text(reading.get("unit")),
        _text(reading.get("error")),
    )


def _add_run(conn: sqlite3.Connection, project_dir: Path, run_id: str) -> None:
    run_dir = _monitoring_dir(project_dir, run_id)
    description = _description(run_dir)
    conn.execute(
        "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        _run_row(project_dir, run_id, description),
    )
    described = {
        var["file"]: var
        for var in description.get("variables") or []
        if isinstance(var, dict)
        and isinstance(var.get("file"), str)
        and isinstance(var.get("component"), str)
        and isinstance(var.get("command"), str)
    }
    for file in sorted(run_dir.glob("*.jsonl")):
        cursor = conn.execute(
            "INSERT INTO variables (run_id, key, component, command, params, file)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (run_id, *_variable(file, described), file.name),
        )
        conn.executemany(
            "INSERT INTO readings VALUES (?, ?, ?, ?, ?, ?, ?)",
            (_reading_row(cursor.lastrowid, reading) for reading in _readings(file)),
        )


def build_database(project_dir: Path, run_ids: Iterable[str], path: Path) -> None:
    """Write the monitoring recordings of *run_ids* to a new SQLite database
    at *path*: tables ``runs``, ``variables`` and ``readings``, and the view
    ``readings_long`` with the CSV's columns."""
    with contextlib.closing(sqlite3.connect(path)) as conn:
        conn.executescript(_SCHEMA)
        conn.execute(f"PRAGMA user_version = {DATABASE_VERSION}")
        for run_id in dict.fromkeys(run_ids):
            _add_run(conn, project_dir, run_id)
        conn.commit()


def _csv_value(value: Any, value_type: str) -> Any:
    if value_type == "boolean":
        return "true" if value else "false"
    return "" if value is None else value


def write_run_csv(conn: sqlite3.Connection, run_id: str, stream: TextIO) -> int:
    """Write *run_id*'s readings, from a database ``build_database`` made, to
    *stream* as CSV: one row per reading, ordered by tick, then variable.
    Returns the number of readings written."""
    writer = csv.writer(stream)
    writer.writerow(CSV_COLUMNS)
    # The view's columns are the CSV's, in order.
    rows = conn.execute(
        "SELECT * FROM readings_long WHERE run_id = ? ORDER BY tick, variable",
        (run_id,),
    )
    value_at = CSV_COLUMNS.index("value")
    count = 0
    for row in rows:
        cells = list(row)
        cells[value_at] = _csv_value(row[value_at], row[value_at + 1])
        writer.writerow(cells)
        count += 1
    return count


def add_monitoring_tables(
    zf: zipfile.ZipFile, project_dir: Path, run_ids: Iterable[str]
) -> dict[str, Any]:
    """Add the monitoring recordings of *run_ids* to *zf*: every reading in
    ``monitoring.db``, and each run's in ``monitoring/{run_id}.csv`` (UTF-8
    with a BOM, so spreadsheets read units like °C right).

    Runs without a recording are left out. Returns the names used:
    ``{"database": "monitoring.db" or None, "csv": {run_id: name}}``.
    """
    recorded = [
        run_id
        for run_id in dict.fromkeys(run_ids)
        if any(_monitoring_dir(project_dir, run_id).glob("*.jsonl"))
    ]
    if not recorded:
        return {"database": None, "csv": {}}
    names: dict[str, str] = {}
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / DATABASE_NAME
        build_database(project_dir, recorded, path)
        # Closed before the folder is removed: Windows keeps an open file.
        with contextlib.closing(sqlite3.connect(path)) as conn:
            for run_id in recorded:
                name = f"{CSV_DIR}/{run_id}.csv"
                with io.TextIOWrapper(
                    zf.open(name, "w"), encoding="utf-8-sig", newline=""
                ) as stream:
                    write_run_csv(conn, run_id, stream)
                names[run_id] = name
        zf.write(path, arcname=DATABASE_NAME)
    return {"database": DATABASE_NAME, "csv": names}
