"""Unit tests for run manifests: written when a run starts, finished when it ends."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime
from unittest.mock import MagicMock

from tests.helpers import MINIMAL_PROCESS_SRC, write_source

from chemunited_workflow.api.run_manifest import manifest_path, write_run_manifest
from chemunited_workflow.api.run_store import RunState, RunStore
from chemunited_workflow.api.services import runner as runner_module
from chemunited_workflow.api.services.export import _parse_log_filename
from chemunited_workflow.api.services.runner import RunnerService
from chemunited_workflow.provenance import GitState

PROTOCOL = {"main_parameter": {}, "my_process_0": {"value": 2.0}}
GIT = GitState(
    commit="a" * 40,
    branch="main",
    dirty=True,
    changed=("protocols_historic/proto.json",),
    captured_at="2026-10-28T09:00:00+01:00",
)


def _make_runner(tmp_path, *, git_state=None, monitoring_service=None):
    (tmp_path / "connectivity").mkdir()
    (tmp_path / "connectivity" / "associations.json").write_text(
        json.dumps({"associations": []}), encoding="utf-8"
    )
    process_dir = tmp_path / "processes"
    process_dir.mkdir()
    write_source(process_dir, "my_process.py", MINIMAL_PROCESS_SRC)
    spec = importlib.util.spec_from_file_location(
        "my_process_manifest", process_dir / "my_process.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["my_process_manifest"] = module
    spec.loader.exec_module(module)

    store = RunStore()
    runner = RunnerService(
        project_dir=tmp_path,
        processes={"my_process": module.MyProcess},
        configs={"my_process": module.MyConfig},
        run_store=store,
        monitoring_service=monitoring_service,
        git_state=git_state,
    )
    return runner, store


def _run(runner, store, sequence=(("my_process", 0),), cancel_reason=None) -> str:
    run_id = store.try_start("proto.json")
    assert run_id is not None
    if cancel_reason is not None:
        store.cancel(cancel_reason)
    runner._execute(
        run_id,
        "proto.json",
        list(sequence),
        PROTOCOL,
        dry_run=True,
        timeout_commands="1 s",
        error_resilient=False,
        record_monitoring=False,
    )
    return run_id


def _manifest(tmp_path, run_id: str) -> dict:
    return json.loads(manifest_path(tmp_path, run_id).read_text(encoding="utf-8"))


def test_a_finished_run_records_what_it_executed(tmp_path):
    runner, store = _make_runner(tmp_path)
    run_id = _run(runner, store)
    manifest = _manifest(tmp_path, run_id)

    assert manifest["schema"] == "chemunited-run-manifest/1"
    assert manifest["run_id"] == run_id
    assert manifest["state"] == "finished"
    assert manifest["reason"] is None
    assert manifest["protocol"] == {"filename": "proto.json", "content": PROTOCOL}
    assert manifest["options"] == {
        "dry_run": True,
        "timeout_commands": "1 s",
        "error_resilient": False,
        "record_monitoring": False,
    }
    assert manifest["project"] == {"name": tmp_path.name, "git": None}
    assert "python" in manifest["software"]

    record = store.get()
    assert record is not None
    assert [result["process"] for result in manifest["results"]] == [
        result.process for result in record.results
    ]
    started = datetime.fromisoformat(manifest["started_at"])
    assert started.tzinfo is not None
    assert started.replace(tzinfo=None) == record.started_at.replace(microsecond=0)
    assert datetime.fromisoformat(manifest["finished_at"]) >= started


def test_the_log_carries_the_run_ids_timestamp(tmp_path):
    runner, store = _make_runner(tmp_path)
    run_id = _run(runner, store)
    (log,) = (tmp_path / "log").glob("*.log")
    assert _parse_log_filename(log.name) == ("proto", run_id)


def test_the_manifest_is_written_when_the_run_starts(tmp_path):
    seen: list[dict] = []
    monitoring = MagicMock()
    runner, store = _make_runner(tmp_path, monitoring_service=monitoring)
    # on_run_started comes after the manifest is first written: read it there.
    monitoring.on_run_started.side_effect = lambda run_id, record: seen.append(
        _manifest(tmp_path, run_id)
    )
    _run(runner, store)
    assert seen[0]["state"] == "running"
    assert seen[0]["finished_at"] is None
    assert seen[0]["results"] == []


def test_a_run_started_right_after_does_not_leave_the_manifest_running(tmp_path):
    monitoring = MagicMock()
    runner, store = _make_runner(tmp_path, monitoring_service=monitoring)
    # on_run_finished comes after the run ended: the next run can start there.
    monitoring.on_run_finished.side_effect = lambda: store.try_start("next.json")
    run_id = _run(runner, store)
    assert _manifest(tmp_path, run_id)["state"] == "finished"


def test_a_failed_run_is_recorded_as_failed(tmp_path):
    runner, store = _make_runner(tmp_path)
    run_id = _run(runner, store, sequence=[("unknown_process", 0)])
    assert _manifest(tmp_path, run_id)["state"] == "failed"


def test_a_cancelled_run_records_why(tmp_path):
    runner, store = _make_runner(tmp_path)
    run_id = _run(runner, store, cancel_reason="interlock tripped")
    manifest = _manifest(tmp_path, run_id)
    assert manifest["state"] == "cancelled"
    assert manifest["reason"] == "interlock tripped"


def test_the_git_state_from_load_is_recorded(tmp_path, monkeypatch):
    monkeypatch.setattr(runner_module, "read_head", lambda project_dir: GIT.commit)
    runner, store = _make_runner(tmp_path, git_state=GIT)
    run_id = _run(runner, store)
    project = _manifest(tmp_path, run_id)["project"]
    assert project["git"] == {
        "commit": GIT.commit,
        "branch": "main",
        "dirty": True,
        "changed": ["protocols_historic/proto.json"],
        "captured_at": GIT.captured_at,
    }
    assert "head_at_start" not in project


def test_a_head_that_moved_since_load_is_recorded_and_warned_about(
    tmp_path, monkeypatch
):
    moved = "b" * 40
    monkeypatch.setattr(runner_module, "read_head", lambda project_dir: moved)
    runner, store = _make_runner(tmp_path, git_state=GIT)
    run_id = _run(runner, store)
    assert _manifest(tmp_path, run_id)["project"]["head_at_start"] == moved
    (log,) = (tmp_path / "log").glob("*.log")
    assert "HEAD moved to bbbbbbb" in log.read_text(encoding="utf-8")


def test_without_a_git_state_head_is_never_read(tmp_path, monkeypatch):
    calls: list = []
    monkeypatch.setattr(runner_module, "read_head", calls.append)
    runner, store = _make_runner(tmp_path)
    _run(runner, store)
    assert calls == []


def test_a_manifest_that_cannot_be_written_does_not_stop_the_run(tmp_path):
    runner, store = _make_runner(tmp_path)
    (tmp_path / "log").mkdir()
    (tmp_path / "log" / "manifests").write_text("in the way", encoding="utf-8")
    _run(runner, store)
    record = store.get()
    assert record is not None
    assert record.state == RunState.FINISHED


def test_write_run_manifest_leaves_no_temporary_file(tmp_path):
    path = tmp_path / "log" / "manifests" / "run.json"
    write_run_manifest(path, {"run_id": "run"})
    assert json.loads(path.read_text(encoding="utf-8")) == {"run_id": "run"}
    assert [p.name for p in path.parent.iterdir()] == ["run.json"]


def test_write_run_manifest_writes_other_values_as_text(tmp_path):
    path = tmp_path / "run.json"
    write_run_manifest(path, {"when": datetime(2026, 1, 1)})
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "when": "2026-01-01 00:00:00"
    }
