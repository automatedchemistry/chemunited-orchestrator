"""Cancellation and late worker callbacks preserve the originating run's identity."""

from datetime import datetime

import pytest

from chemunited_workflow.api.run_store import RunState, RunStore
from chemunited_workflow.enums import WorkflowEventType
from chemunited_workflow.models import WorkflowExecutionEvent, WorkflowResult


@pytest.mark.parametrize("cancelled", [False, True])
def test_worker_retains_slot_until_cleanup_releases_execution(tmp_path, cancelled):
    store = RunStore(tmp_path)
    record = store.try_start_record("source.json", execution_active=True)
    assert record is not None
    if cancelled:
        assert store.cancel("Operator stopped")
        assert record.cancel_event.is_set()
    else:
        store.set_state(success=True, record=record)
    assert record.state == (RunState.CANCELLED if cancelled else RunState.FINISHED)
    assert store.try_start_record("next.json") is None
    assert store.active_run_id == record.run_id
    assert (tmp_path / "run.lock").exists()

    store.release_execution(record)

    assert store.active_run_id is None
    assert not (tmp_path / "run.lock").exists()
    assert store.try_start_record("next.json") is not None


def test_late_callbacks_cannot_modify_a_same_id_replacement(tmp_path, monkeypatch):
    from chemunited_workflow.api import run_store

    class Clock(datetime):
        @classmethod
        def now(cls):
            return cls(2026, 11, 12, 12, 0, 0)

    monkeypatch.setattr(run_store, "datetime", Clock)
    store = RunStore(tmp_path)
    old = store.try_start_record("source.json", execution_active=True)
    assert store.cancel("Old run stopped")
    store.release_execution(old)
    current = store.try_start_record(
        "source.json", protocol_plan={"marker": "current"}, execution_active=True
    )
    assert current is not old
    assert current.run_id == old.run_id
    event = WorkflowExecutionEvent(
        event_type=WorkflowEventType.EXECUTION_FINISHED, message="Late old event"
    )
    result = WorkflowResult(node_state={}, node_result={}, node_runtime={}, errors={})

    store.append_event(event, record=old)
    store.append_result(result, record=old)
    store.set_protocol_plan({"marker": "old"}, record=old)
    store.set_current_occurrence({"execution_key": "old_9"}, record=old)
    prompt = store.request_input("old_9::ask", "Old prompt", record=old)
    store.set_state(success=False, record=old)
    store.release_execution(old)

    assert current.state == RunState.RUNNING
    assert current.execution_active
    assert not current.cancel_event.is_set()
    assert current.events == current.results == []
    assert current.protocol_plan == {"marker": "current"}
    assert current.current_occurrence is None
    assert current.pending_inputs == {}
    assert store.pop_input_value("old_9::ask", record=old) is None
    assert old.events == [event]
    assert old.results == [result]
    assert not prompt.is_set()
    assert (tmp_path / "run.lock").exists()


def test_same_node_prompts_require_a_unique_occurrence_or_explicit_key():
    store = RunStore()
    record = store.try_start_record("source.json")
    first = store.request_input("work_0::confirm", "First", record=record)
    second = store.request_input("work_1::confirm", "Second", record=record)
    assert not store.submit_input("confirm", "Ambiguous")
    assert not first.is_set() and not second.is_set()
    assert store.submit_input("work_0::confirm", "First answer")
    assert first.is_set() and not second.is_set()
    assert store.pop_input_value("work_0::confirm", record=record) == "First answer"
    assert store.submit_input("confirm", "Unique remaining answer")
    assert second.is_set()
    assert (
        store.pop_input_value("work_1::confirm", record=record)
        == "Unique remaining answer"
    )
