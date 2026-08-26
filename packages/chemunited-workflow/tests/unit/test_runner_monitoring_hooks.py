"""Unit tests for RunnerService's monitoring on_run_started/on_run_finished wiring."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from chemunited_workflow.api.monitoring_store import MonitoringStore
from chemunited_workflow.api.run_store import RunStore
from chemunited_workflow.api.services.monitoring import MonitoringService
from chemunited_workflow.api.services.runner import RunnerService
from tests.helpers import MINIMAL_PROCESS_SRC, write_source


def _make_runner(tmp_path, monitoring_service=None) -> tuple[RunnerService, RunStore]:
    connectivity_dir = tmp_path / "connectivity"
    connectivity_dir.mkdir()
    (connectivity_dir / "associations.json").write_text(
        json.dumps({"associations": []}), encoding="utf-8"
    )
    process_dir = tmp_path / "processes"
    process_dir.mkdir()
    write_source(process_dir, "my_process.py", MINIMAL_PROCESS_SRC)

    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location(
        "my_process_hooks", process_dir / "my_process.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["my_process_hooks"] = mod
    spec.loader.exec_module(mod)

    store = RunStore()
    runner = RunnerService(
        project_dir=tmp_path,
        processes={"my_process": mod.MyProcess},
        configs={"my_process": mod.MyConfig},
        run_store=store,
        monitoring_service=monitoring_service,
    )
    return runner, store


def test_execute_calls_on_run_started_and_finished_with_run_id_and_record_flag(
    tmp_path,
):
    monitoring = MagicMock()
    runner, store = _make_runner(tmp_path, monitoring_service=monitoring)
    run_id = store.try_start("proto.json")
    assert run_id is not None

    runner._execute(
        run_id,
        "proto.json",
        [("my_process", 0)],
        {"my_process_0": {}},
        dry_run=True,
        timeout_commands="1 s",
        error_resilient=False,
        record_monitoring=True,
    )

    monitoring.on_run_started.assert_called_once_with(run_id, record=True)
    monitoring.on_run_finished.assert_called_once_with()


def test_execute_calls_on_run_finished_even_when_run_fails(tmp_path):
    monitoring = MagicMock()
    runner, store = _make_runner(tmp_path, monitoring_service=monitoring)
    run_id = store.try_start("proto.json")
    assert run_id is not None

    # An unknown process name makes _execute raise before completing the sequence.
    runner._execute(
        run_id,
        "proto.json",
        [("no_such_process", 0)],
        {},
        dry_run=True,
        timeout_commands="1 s",
        error_resilient=False,
        record_monitoring=False,
    )

    monitoring.on_run_started.assert_called_once_with(run_id, record=False)
    monitoring.on_run_finished.assert_called_once_with()


def test_execute_without_monitoring_service_does_not_raise(tmp_path):
    runner, store = _make_runner(tmp_path, monitoring_service=None)
    run_id = store.try_start("proto.json")
    assert run_id is not None

    runner._execute(
        run_id,
        "proto.json",
        [("my_process", 0)],
        {"my_process_0": {}},
        dry_run=True,
        timeout_commands="1 s",
        error_resilient=False,
        record_monitoring=False,
    )  # must not raise


# ── start() hard-error validation for record_monitoring ─────────────────────


def test_start_raises_when_record_monitoring_and_no_variables_configured(tmp_path):
    """No monitoring.json written -> MonitoringService.read_config() defaults
    to an empty variables list, matching a fresh project that never called
    PUT /monitoring/config."""
    monitoring = MonitoringService(project_dir=tmp_path, store=MonitoringStore())
    runner, store = _make_runner(tmp_path, monitoring_service=monitoring)

    with pytest.raises(ValueError, match="no monitoring variables"):
        runner.start("proto.json", record_monitoring=True)

    # The run must never have been created — try_start() is called after
    # the validation, so a rejected request can't consume the one-run slot.
    assert store.active_run_id is None


def test_start_raises_when_record_monitoring_and_no_monitoring_service(tmp_path):
    runner, store = _make_runner(tmp_path, monitoring_service=None)

    with pytest.raises(ValueError, match="monitoring is not available"):
        runner.start("proto.json", record_monitoring=True)

    assert store.active_run_id is None


def test_start_without_record_monitoring_ignores_missing_monitoring_config(tmp_path):
    """record_monitoring=False (the default) never touches monitoring at all,
    so a missing/empty monitoring config must not block a normal run."""
    runner, store = _make_runner(tmp_path, monitoring_service=None)

    (tmp_path / "protocols_historic").mkdir()
    (tmp_path / "protocols_historic" / "proto.json").write_text(
        json.dumps({"my_process_0": {}}), encoding="utf-8"
    )

    run_id = runner.start("proto.json")  # must not raise

    assert run_id is not None
