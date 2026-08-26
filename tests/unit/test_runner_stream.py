"""Unit tests for run SSE streaming."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from chemunited_workflow.api.routers.runner import _generate_run_stream
from chemunited_workflow.api.run_store import RunStore
from chemunited_workflow.api.services.runner import RunnerService
from chemunited_workflow.enums import WorkflowEventType
from chemunited_workflow.models import WorkflowExecutionEvent


def test_run_stream_sends_heartbeat_until_finished():
    async def collect_chunks() -> tuple[str, str]:
        store = RunStore()
        run_id = store.try_start("p_2026-01-01T00-00-00.json")
        assert run_id is not None
        svc = RunnerService(Path(), {}, {}, store)
        stream = _generate_run_stream(
            svc,
            poll_interval=0.0,
            heartbeat_interval=0.0,
        )

        heartbeat = await anext(stream)
        store.set_state(success=True)
        terminal = await anext(stream)
        with pytest.raises(StopAsyncIteration):
            await anext(stream)
        return heartbeat, terminal

    heartbeat, terminal = asyncio.run(collect_chunks())

    assert heartbeat == ": heartbeat\n\n"
    assert terminal == 'data: {"state": "finished"}\n\n'


def test_run_stream_drains_events_appended_right_before_finish():
    """A fast run can append its last events and flip to FINISHED entirely
    inside one poll sleep. Regression test for a race where the loop's
    `while state == RUNNING` check (evaluated *before* the next drain) would
    skip that final batch of events instead of streaming them.
    """

    async def collect_chunks() -> list[str]:
        store = RunStore()
        run_id = store.try_start("p_2026-01-01T00-00-00.json")
        assert run_id is not None
        svc = RunnerService(Path(), {}, {}, store)
        stream = _generate_run_stream(
            svc,
            poll_interval=0.0,
            heartbeat_interval=0.0,
        )

        heartbeat = await anext(stream)

        # Simulate events landing in the same window the run finishes in —
        # nothing pops them until after `state` has already left RUNNING.
        store.append_event(
            WorkflowExecutionEvent(
                event_type=WorkflowEventType.NODE_COMPLETED,
                message="last node ran",
                node_key=("script_1", 0),
            )
        )
        store.set_state(success=True)

        chunks = [heartbeat]
        while True:
            chunk = await anext(stream)
            chunks.append(chunk)
            if chunk.startswith('data: {"state"'):
                break
        return chunks

    chunks = asyncio.run(collect_chunks())

    assert any(
        "last node ran" in c for c in chunks
    ), f"Event appended just before the state flip was dropped: {chunks}"
    assert chunks[-1] == 'data: {"state": "finished"}\n\n'
