"""Unit tests for the export service — one row per executed run, correlated
by filename convention, with zip/clean scoped to a selection of runs."""

from __future__ import annotations

import io
import zipfile

import pytest

from chemunited_workflow.api.services.export import (
    _parse_log_filename,
    build_zip,
    clean,
    default_build_zip,
    default_clean,
    load_export_hooks,
    preview,
)

RUN1_LOG = "test_2026-01-01T00-00-00_executed_2026-01-02T10-00-00.log"
RUN1_ID = "test_2026-01-01T00-00-00_2026-01-02T10-00-00"
RUN2_LOG = "test_2026-01-01T00-00-00_executed_2026-01-03T11-00-00.log"
RUN2_ID = "test_2026-01-01T00-00-00_2026-01-03T11-00-00"
RUN3_LOG = "gone_2026-01-01T00-00-00_executed_2026-01-04T12-00-00.log"
WEIRD_LOG = "weird.log"


def _write_hook(tmp_path, body: str) -> None:
    hook_dir = tmp_path / "customizations" / "export"
    hook_dir.mkdir(parents=True, exist_ok=True)
    (hook_dir / "export_hook.py").write_text(body, encoding="utf-8")


def _make_project(tmp_path):
    (tmp_path / "log").mkdir()
    (tmp_path / "protocols_historic").mkdir()

    # Run 1: log + monitoring + protocol, all present.
    (tmp_path / "protocols_historic" / "test_2026-01-01T00-00-00.json").write_text(
        "{}", encoding="utf-8"
    )
    (tmp_path / "log" / RUN1_LOG).write_text("log1", encoding="utf-8")
    run1_dir = tmp_path / "log" / "monitoring" / RUN1_ID
    run1_dir.mkdir(parents=True)
    (run1_dir / "chiller__temperature.jsonl").write_text(
        '{"tick": 0}\n', encoding="utf-8"
    )

    # Run 2: second execution of the same protocol, no monitoring recorded.
    (tmp_path / "log" / RUN2_LOG).write_text("log2", encoding="utf-8")

    # Run 3: log exists but its protocol was deleted from protocols_historic/.
    (tmp_path / "log" / RUN3_LOG).write_text("log3", encoding="utf-8")

    # A log filename that doesn't follow the _executed_ convention at all.
    (tmp_path / "log" / WEIRD_LOG).write_text("log4", encoding="utf-8")

    return tmp_path


# ── _parse_log_filename ──────────────────────────────────────────────────────


def test_parse_log_filename_well_formed():
    assert _parse_log_filename(RUN1_LOG) == ("test_2026-01-01T00-00-00", RUN1_ID)


def test_parse_log_filename_malformed_returns_none():
    assert _parse_log_filename(WEIRD_LOG) is None


# ── load_export_hooks ────────────────────────────────────────────────────────


def test_load_export_hooks_missing_file_returns_empty(tmp_path):
    assert load_export_hooks(tmp_path) == {}


def test_load_export_hooks_loads_registered_dict(tmp_path):
    _write_hook(
        tmp_path,
        "def build_zip(project_dir, logs):\n    return b'custom'\n"
        "EXPORT_HOOKS = {'build_zip': build_zip}\n",
    )
    hooks = load_export_hooks(tmp_path)
    assert set(hooks) == {"build_zip"}
    assert hooks["build_zip"](tmp_path, []) == b"custom"


def test_load_export_hooks_missing_export_returns_empty(tmp_path):
    _write_hook(tmp_path, "NOT_THE_RIGHT_NAME = {}\n")
    assert load_export_hooks(tmp_path) == {}


def test_load_export_hooks_broken_file_returns_empty_without_raising(tmp_path):
    _write_hook(tmp_path, "raise RuntimeError('boom')\n")
    assert load_export_hooks(tmp_path) == {}


# ── preview ───────────────────────────────────────────────────────────────────


def test_preview_empty_project(tmp_path):
    (tmp_path / "log").mkdir()
    assert preview(tmp_path) == []


def test_preview_one_row_per_log_with_correlation(tmp_path):
    _make_project(tmp_path)
    rows = {r["log"]["filename"]: r for r in preview(tmp_path)}

    assert set(rows) == {RUN1_LOG, RUN2_LOG, RUN3_LOG, WEIRD_LOG}

    run1 = rows[RUN1_LOG]
    assert run1["monitoring"]["run_id"] == RUN1_ID
    assert [f["filename"] for f in run1["monitoring"]["files"]] == [
        f"{RUN1_ID}/chiller__temperature.jsonl"
    ]
    assert run1["protocol"]["filename"] == "test_2026-01-01T00-00-00.json"

    run2 = rows[RUN2_LOG]
    assert run2["monitoring"] is None
    assert run2["protocol"]["filename"] == "test_2026-01-01T00-00-00.json"

    run3 = rows[RUN3_LOG]
    assert run3["monitoring"] is None
    assert run3["protocol"] is None

    weird = rows[WEIRD_LOG]
    assert weird["monitoring"] is None
    assert weird["protocol"] is None


# ── default_build_zip / build_zip ────────────────────────────────────────────


def test_default_build_zip_scoped_to_selection(tmp_path):
    _make_project(tmp_path)
    content = default_build_zip(tmp_path, [RUN1_LOG])
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        names = set(zf.namelist())
    assert names == {
        f"log/{RUN1_LOG}",
        f"log/monitoring/{RUN1_ID}/chiller__temperature.jsonl",
        "protocols_historic/test_2026-01-01T00-00-00.json",
    }


def test_default_build_zip_dedupes_shared_protocol(tmp_path):
    _make_project(tmp_path)
    content = default_build_zip(tmp_path, [RUN1_LOG, RUN2_LOG])
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        names = zf.namelist()
    assert names.count("protocols_historic/test_2026-01-01T00-00-00.json") == 1
    assert f"log/{RUN1_LOG}" in names
    assert f"log/{RUN2_LOG}" in names


def test_default_build_zip_skips_unknown_filename(tmp_path):
    _make_project(tmp_path)
    content = default_build_zip(tmp_path, [RUN1_LOG, "missing.log"])
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        names = zf.namelist()
    assert f"log/{RUN1_LOG}" in names
    assert not any("missing" in n for n in names)


def test_default_build_zip_rejects_path_traversal(tmp_path):
    _make_project(tmp_path)
    content = default_build_zip(
        tmp_path, ["../protocols_historic/test_2026-01-01T00-00-00.json"]
    )
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        assert zf.namelist() == []


def test_default_build_zip_never_deletes_source_files(tmp_path):
    _make_project(tmp_path)
    default_build_zip(tmp_path, [RUN1_LOG])
    assert (tmp_path / "log" / RUN1_LOG).exists()
    assert (tmp_path / "log" / "monitoring" / RUN1_ID).exists()


def test_build_zip_uses_hook_when_registered(tmp_path):
    _make_project(tmp_path)
    _write_hook(
        tmp_path,
        "def build_zip(project_dir, logs):\n    return b'from-hook'\n"
        "EXPORT_HOOKS = {'build_zip': build_zip}\n",
    )
    assert build_zip(tmp_path, [RUN1_LOG]) == b"from-hook"


def test_build_zip_falls_back_to_default_without_hook(tmp_path):
    _make_project(tmp_path)
    content = build_zip(tmp_path, [RUN1_LOG])
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        assert f"log/{RUN1_LOG}" in zf.namelist()


def test_build_zip_propagates_hook_exception(tmp_path):
    _make_project(tmp_path)
    _write_hook(
        tmp_path,
        "def build_zip(project_dir, logs):\n    raise ValueError('nope')\n"
        "EXPORT_HOOKS = {'build_zip': build_zip}\n",
    )
    with pytest.raises(ValueError, match="nope"):
        build_zip(tmp_path, [RUN1_LOG])


# ── default_clean / clean ────────────────────────────────────────────────────


def test_default_clean_scoped_to_selection(tmp_path):
    _make_project(tmp_path)
    result = default_clean(tmp_path, [RUN1_LOG])
    assert set(result["deleted"]) == {
        f"log/{RUN1_LOG}",
        f"log/monitoring/{RUN1_ID}/chiller__temperature.jsonl",
    }
    assert result["count"] == 2
    assert not (tmp_path / "log" / RUN1_LOG).exists()
    assert not (tmp_path / "log" / "monitoring" / RUN1_ID).exists()
    # unrelated runs untouched
    assert (tmp_path / "log" / RUN2_LOG).exists()
    assert (tmp_path / "log" / RUN3_LOG).exists()


def test_default_clean_never_touches_protocols_historic(tmp_path):
    _make_project(tmp_path)
    default_clean(tmp_path, [RUN1_LOG, RUN2_LOG])
    assert (tmp_path / "protocols_historic" / "test_2026-01-01T00-00-00.json").exists()


def test_default_clean_skips_unknown_filename(tmp_path):
    _make_project(tmp_path)
    result = default_clean(tmp_path, ["missing.log"])
    assert result == {"deleted": [], "count": 0}


def test_default_clean_rejects_path_traversal(tmp_path):
    _make_project(tmp_path)
    result = default_clean(
        tmp_path, ["../protocols_historic/test_2026-01-01T00-00-00.json"]
    )
    assert result == {"deleted": [], "count": 0}
    assert (tmp_path / "protocols_historic" / "test_2026-01-01T00-00-00.json").exists()


def test_clean_uses_hook_when_registered(tmp_path):
    _make_project(tmp_path)
    _write_hook(
        tmp_path,
        "def clean(project_dir, logs):\n"
        "    return {'deleted': ['custom.txt'], 'count': 1}\n"
        "EXPORT_HOOKS = {'clean': clean}\n",
    )
    result = clean(tmp_path, [RUN1_LOG])
    assert result == {"deleted": ["custom.txt"], "count": 1}
    # hook fully replaces default behavior — files untouched by the hook stay put
    assert (tmp_path / "log" / RUN1_LOG).exists()


def test_clean_falls_back_to_default_without_hook(tmp_path):
    _make_project(tmp_path)
    result = clean(tmp_path, [RUN1_LOG])
    assert result["count"] == 2
    assert not (tmp_path / "log" / RUN1_LOG).exists()


def test_clean_propagates_hook_exception(tmp_path):
    _make_project(tmp_path)
    _write_hook(
        tmp_path,
        "def clean(project_dir, logs):\n    raise ValueError('nope')\n"
        "EXPORT_HOOKS = {'clean': clean}\n",
    )
    with pytest.raises(ValueError, match="nope"):
        clean(tmp_path, [RUN1_LOG])


def test_partial_hook_overrides_only_clean(tmp_path):
    _make_project(tmp_path)
    _write_hook(
        tmp_path,
        "def clean(project_dir, logs):\n    return {'deleted': [], 'count': 0}\n"
        "EXPORT_HOOKS = {'clean': clean}\n",
    )
    # build_zip still uses the default since the hook only overrides clean
    content = build_zip(tmp_path, [RUN1_LOG])
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        assert f"log/{RUN1_LOG}" in zf.namelist()
    assert clean(tmp_path, [RUN1_LOG]) == {"deleted": [], "count": 0}
