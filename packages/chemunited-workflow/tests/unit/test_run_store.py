"""Unit tests for the singleton RunStore."""

from __future__ import annotations

import threading

from chemunited_workflow.api.run_store import RunState, RunStore
from chemunited_workflow.enums import WorkflowEventType
from chemunited_workflow.models import WorkflowExecutionEvent


def _make_event(msg: str = "test") -> WorkflowExecutionEvent:
    return WorkflowExecutionEvent(
        event_type=WorkflowEventType.NODE_RUNNING, message=msg
    )


def test_try_start_returns_derived_id():
    store = RunStore()
    run_id = store.try_start("suzuki_batch_2026-05-15T10-38-00.json")
    assert run_id is not None
    assert run_id.startswith("suzuki_batch_2026-05-15T10-38-00_")


def test_try_start_rejects_second_call_while_running():
    store = RunStore()
    first = store.try_start("my_protocol_2026-01-01T00-00-00.json")
    assert first is not None
    second = store.try_start("other_2026-01-01T00-00-01.json")
    assert second is None


def test_try_start_allowed_after_terminal_state():
    store = RunStore()
    store.try_start("protocol_2026-01-01T00-00-00.json")
    store.set_state(success=True)
    run_id = store.try_start("protocol_2026-01-01T00-00-01.json")
    assert run_id is not None


def test_pop_events_returns_appended_and_clears():
    store = RunStore()
    store.try_start("p_2026-01-01T00-00-00.json")
    e1 = _make_event("a")
    e2 = _make_event("b")
    store.append_event(e1)
    store.append_event(e2)
    events = store.pop_events()
    assert len(events) == 2
    assert events[0].message == "a"
    assert events[1].message == "b"
    assert store.pop_events() == []


def test_cancel_running_returns_true():
    store = RunStore()
    store.try_start("p_2026-01-01T00-00-00.json")
    cancel_event = store.cancel_event()
    assert cancel_event is not None
    assert not cancel_event.is_set()

    result = store.cancel()

    assert result is True
    assert store.get().state == RunState.CANCELLED
    assert cancel_event.is_set()


def test_cancelled_state_is_sticky():
    store = RunStore()
    store.try_start("p_2026-01-01T00-00-00.json")
    assert store.cancel() is True
    store.set_state(success=True)
    assert store.get().state == RunState.CANCELLED


def test_cancel_after_finished_returns_false():
    store = RunStore()
    store.try_start("p_2026-01-01T00-00-00.json")
    store.set_state(success=True)
    assert store.cancel() is False


def test_pause_running_returns_true_and_sets_state_and_event():
    store = RunStore()
    store.try_start("p_2026-01-01T00-00-00.json")
    pause_event = store.pause_event()
    assert pause_event is not None
    assert not pause_event.is_set()

    result = store.pause()

    assert result is True
    assert store.get().state == RunState.PAUSED
    assert pause_event.is_set()


def test_pause_when_not_running_returns_false():
    store = RunStore()
    assert store.pause() is False  # no run at all
    store.try_start("p_2026-01-01T00-00-00.json")
    store.pause()
    assert store.pause() is False  # already paused


def test_resume_paused_returns_true_and_clears_event():
    store = RunStore()
    store.try_start("p_2026-01-01T00-00-00.json")
    store.pause()
    pause_event = store.pause_event()

    result = store.resume()

    assert result is True
    assert store.get().state == RunState.RUNNING
    assert not pause_event.is_set()


def test_resume_when_not_paused_returns_false():
    store = RunStore()
    store.try_start("p_2026-01-01T00-00-00.json")
    assert store.resume() is False  # still running, never paused


def test_cancel_from_paused_returns_true_and_clears_pause_event():
    store = RunStore()
    store.try_start("p_2026-01-01T00-00-00.json")
    store.pause()
    pause_event = store.pause_event()

    result = store.cancel()

    assert result is True
    assert store.get().state == RunState.CANCELLED
    assert not pause_event.is_set()  # wakes anything blocked on the pause checkpoint


def test_try_start_rejects_second_call_while_paused():
    store = RunStore()
    store.try_start("p_2026-01-01T00-00-00.json")
    store.pause()
    assert store.try_start("other_2026-01-01T00-00-01.json") is None


def test_active_run_id_returns_run_id_while_paused():
    store = RunStore()
    run_id = store.try_start("p_2026-01-01T00-00-00.json")
    store.pause()
    assert store.active_run_id == run_id


def test_pause_event_returns_none_with_no_run():
    store = RunStore()
    assert store.pause_event() is None


def test_active_run_id_returns_run_id_while_running():
    store = RunStore()
    run_id = store.try_start("p_2026-01-01T00-00-00.json")
    assert store.active_run_id == run_id


def test_active_run_id_none_when_finished():
    store = RunStore()
    store.try_start("p_2026-01-01T00-00-00.json")
    store.set_state(success=True)
    assert store.active_run_id is None


def test_set_state_finished():
    store = RunStore()
    store.try_start("p_2026-01-01T00-00-00.json")
    store.set_state(success=True)
    assert store.get().state == RunState.FINISHED


def test_set_state_failed():
    store = RunStore()
    store.try_start("p_2026-01-01T00-00-00.json")
    store.set_state(success=False)
    assert store.get().state == RunState.FAILED


def test_get_returns_none_with_no_run():
    store = RunStore()
    assert store.get() is None


def test_pop_events_returns_empty_with_no_run():
    store = RunStore()
    assert store.pop_events() == []


def test_cancel_event_returns_none_with_no_run():
    store = RunStore()
    assert store.cancel_event() is None


def test_thread_safe_append_events():
    """50 threads each append one event — all 50 should be retrieved."""
    store = RunStore()
    store.try_start("p_2026-01-01T00-00-00.json")
    barrier = threading.Barrier(50)
    errors: list[Exception] = []

    def append_one(i: int):
        try:
            barrier.wait()
            store.append_event(_make_event(str(i)))
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=append_one, args=(i,)) for i in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    events = store.pop_events()
    assert len(events) == 50


def test_lockfile_written_on_start(tmp_path):
    store = RunStore(project_dir=tmp_path)
    store.try_start("p_2026-01-01T00-00-00.json")
    assert (tmp_path / "run.lock").exists()


def test_lockfile_deleted_on_finish(tmp_path):
    store = RunStore(project_dir=tmp_path)
    store.try_start("p_2026-01-01T00-00-00.json")
    store.set_state(success=True)
    assert not (tmp_path / "run.lock").exists()


def test_lockfile_deleted_on_cancel(tmp_path):
    store = RunStore(project_dir=tmp_path)
    store.try_start("p_2026-01-01T00-00-00.json")
    store.cancel()
    assert not (tmp_path / "run.lock").exists()


def test_lockfile_restores_running_state_on_startup(tmp_path):
    import json

    (tmp_path / "run.lock").write_text(
        json.dumps({"run_id": "stale_run", "state": "running"}),
        encoding="utf-8",
    )
    store = RunStore(project_dir=tmp_path)
    assert store.active_run_id == "stale_run"
    assert store.try_start("new_p_2026-01-01T00-00-00.json") is None


def test_set_project_dir_restores_lockfile(tmp_path):
    import json

    (tmp_path / "run.lock").write_text(
        json.dumps({"run_id": "stale_run", "state": "running"}),
        encoding="utf-8",
    )
    store = RunStore()
    assert store.active_run_id is None
    store.set_project_dir(tmp_path)
    assert store.active_run_id == "stale_run"


# ── pending operator input ───────────────────────────────────────────────────


def test_request_input_registers_prompt_and_returns_unset_event():
    store = RunStore()
    store.try_start("p_2026-01-01T00-00-00.json")
    event = store.request_input("dispense", "Confirm reagent loaded")
    assert not event.is_set()
    assert store.pending_input_prompts() == {"dispense": "Confirm reagent loaded"}


def test_submit_input_sets_event_and_value_then_pop_clears_it():
    store = RunStore()
    store.try_start("p_2026-01-01T00-00-00.json")
    event = store.request_input("dispense", "Confirm reagent loaded")

    assert store.submit_input("dispense", "yes") is True
    assert event.is_set()
    assert store.pop_input_value("dispense") == "yes"
    # cleared after popping
    assert store.pending_input_prompts() == {}
    assert store.pop_input_value("dispense") is None


def test_submit_input_returns_false_when_nothing_pending():
    store = RunStore()
    store.try_start("p_2026-01-01T00-00-00.json")
    assert store.submit_input("no_such_node", "yes") is False


def test_pending_inputs_are_scoped_per_node():
    store = RunStore()
    store.try_start("p_2026-01-01T00-00-00.json")
    event_a = store.request_input("node_a", "A?")
    event_b = store.request_input("node_b", "B?")

    store.submit_input("node_a", "reply-a")

    assert event_a.is_set()
    assert not event_b.is_set()
    assert store.pop_input_value("node_a") == "reply-a"
    assert store.pending_input_prompts() == {"node_b": "B?"}


def test_cancel_wakes_pending_input_events():
    store = RunStore()
    store.try_start("p_2026-01-01T00-00-00.json")
    event = store.request_input("dispense", "Confirm reagent loaded")

    store.cancel()

    assert event.is_set()
    # No reply was actually delivered — the caller must observe cancellation
    # via cancel_event, not treat this wake-up as a real answer.
    assert store.pop_input_value("dispense") is None
