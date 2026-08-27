"""Unit tests for the POST /run/input endpoint and GET /run/active's pending_inputs."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from chemunited_workflow.api.project_holder import ProjectHolder
from chemunited_workflow.api.routers.runner import get_active_run, submit_run_input
from chemunited_workflow.api.run_store import RunStore
from chemunited_workflow.api.schemas import RunInputIn
from chemunited_workflow.api.services.runner import RunnerService


def test_get_active_run_reports_no_pending_inputs_by_default():
    holder = ProjectHolder()
    holder.run_store.try_start("p_2026-01-01T00-00-00.json")

    result = _run(get_active_run(holder))

    assert result["pending_inputs"] == {}


def test_get_active_run_reports_pending_input_prompts():
    holder = ProjectHolder()
    holder.run_store.try_start("p_2026-01-01T00-00-00.json")
    holder.run_store.request_input("dispense", "Confirm reagent loaded")

    result = _run(get_active_run(holder))

    assert result["pending_inputs"] == {"dispense": "Confirm reagent loaded"}


def test_submit_run_input_delivers_reply():
    store = RunStore()
    store.try_start("p_2026-01-01T00-00-00.json")
    svc = RunnerService(Path(), {}, {}, store)
    event = store.request_input("dispense", "Confirm reagent loaded")

    _run(submit_run_input(RunInputIn(node_id="dispense", value="yes"), svc))

    assert event.is_set()
    assert store.pop_input_value("dispense") == "yes"


def test_submit_run_input_404_when_nothing_pending():
    store = RunStore()
    store.try_start("p_2026-01-01T00-00-00.json")
    svc = RunnerService(Path(), {}, {}, store)

    with pytest.raises(HTTPException) as exc_info:
        _run(submit_run_input(RunInputIn(node_id="no_such_node", value="yes"), svc))

    assert exc_info.value.status_code == 404


def _run(coro):
    import asyncio

    return asyncio.run(coro)
