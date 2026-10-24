"""Tests for the command events device clients report (live platform view, step 2)."""

from __future__ import annotations

import threading

import networkx as nx
import pytest
import requests
import responses as resp_lib
from pydantic import BaseModel

from chemunited_workflow import (
    NodeExecutionContext,
    Process,
    WorkflowEdgeSpec,
    WorkflowExecutor,
    WorkflowNodeSpec,
    compile_workflow,
)
from chemunited_workflow.clients import BaseClient, ComponentClient
from chemunited_workflow.clients.base import _pop_thread_resilient_errors
from chemunited_workflow.command_events import CommandEvent
from chemunited_workflow.exceptions import RunCancelledError

DEVICE = "events-test-pump"
URL = f"http://device-server:8000/sim/{DEVICE}"


def _response(body: bytes = b"{}") -> requests.Response:
    response = requests.Response()
    response.status_code = 200
    response._content = body
    response.headers["Content-Type"] = "application/json"
    return response


@pytest.fixture
def events() -> list[CommandEvent]:
    return []


def _client(events: list[CommandEvent], **kwargs) -> ComponentClient:
    return ComponentClient(
        URL, component_ui=DEVICE, command_observer=events.append, **kwargs
    )


def _kinds(events: list[CommandEvent]) -> list[str]:
    return [event.kind for event in events]


def test_a_put_reports_started_then_finished(mocker, events):
    mocker.patch.object(BaseClient, "put", return_value=_response())
    mocker.patch.object(BaseClient, "get", return_value=_response(b"true"))

    _client(events).put("infuse", volume="1 ml")

    assert _kinds(events) == ["started", "finished"]
    for event in events:
        assert event.component == DEVICE
        assert event.command == "infuse"
        assert event.params == {"volume": "1 ml"}
        assert event.error is None


def test_started_goes_out_before_the_request_and_finished_after_the_wait(
    mocker, events
):
    seen_during_request: list[list[str]] = []
    seen_during_wait: list[list[str]] = []
    idle_answers = iter([b"false", b"false", b"true"])

    def put(self, path, **kwargs):
        seen_during_request.append(_kinds(events))
        return _response()

    def get(self, path, **kwargs):
        seen_during_wait.append(_kinds(events))
        return _response(next(idle_answers))

    mocker.patch.object(BaseClient, "put", put)
    mocker.patch.object(BaseClient, "get", get)
    mocker.patch.object(ComponentClient, "_sleep_interruptibly")

    _client(events).put("infuse")

    assert seen_during_request == [["started"]]
    assert seen_during_wait == [["started"]] * 3
    assert _kinds(events) == ["started", "finished"]


def test_a_post_reports_its_json_body(mocker, events):
    mocker.patch.object(BaseClient, "post", return_value=_response())
    mocker.patch.object(BaseClient, "get", return_value=_response(b"true"))

    _client(events).post("method", json={"steps": [1, 2]})

    assert events[0].body == {"steps": [1, 2]}
    assert events[0].params is None


def test_a_get_reports_nothing(mocker, events):
    mocker.patch.object(BaseClient, "get", return_value=_response(b"1.0"))

    assert _client(events).get("value") == 1.0
    assert events == []


@resp_lib.activate
def test_an_http_error_reports_failed_and_still_raises(events):
    resp_lib.add(resp_lib.PUT, f"{URL}/infuse", status=500, body=b"boom")

    with pytest.raises(requests.HTTPError):
        _client(events).put("infuse")

    assert _kinds(events) == ["started", "failed"]
    assert "500" in events[1].error


@resp_lib.activate
def test_a_resilient_error_reports_failed_and_is_still_left_for_the_executor(events):
    resp_lib.add(resp_lib.PUT, f"{URL}/infuse", status=500, body=b"boom")
    resp_lib.add(resp_lib.GET, f"{URL}/is-idle", status=200, body=b"true")
    _pop_thread_resilient_errors()

    assert _client(events, error_resilient=True).put("infuse") == {}

    assert _kinds(events) == ["started", "failed"]
    assert "500" in events[1].error
    errors = _pop_thread_resilient_errors()
    assert len(errors) == 1 and isinstance(errors[0], requests.HTTPError)


def test_an_idle_timeout_reports_failed(mocker, events):
    mocker.patch.object(BaseClient, "put", return_value=_response())
    mocker.patch.object(BaseClient, "get", return_value=_response(b"false"))
    mocker.patch.object(ComponentClient, "_sleep_interruptibly")

    with pytest.raises(TimeoutError):
        _client(events, timeout_commands="0.01 s").put("infuse")

    assert _kinds(events) == ["started", "failed"]
    assert "idle" in events[1].error


def test_a_resilient_idle_timeout_reports_failed(mocker, events):
    mocker.patch.object(BaseClient, "put", return_value=_response())
    mocker.patch.object(BaseClient, "get", return_value=_response(b"false"))
    mocker.patch.object(ComponentClient, "_sleep_interruptibly")
    _pop_thread_resilient_errors()

    _client(events, timeout_commands="0.01 s", error_resilient=True).put("infuse")

    assert _kinds(events) == ["started", "failed"]
    assert isinstance(_pop_thread_resilient_errors()[0], TimeoutError)


def test_cancelling_during_the_wait_reports_failed(mocker, events):
    cancel = threading.Event()

    def get(self, path, **kwargs):
        cancel.set()  # the run is cancelled while the device is still busy
        return _response(b"false")

    mocker.patch.object(BaseClient, "put", return_value=_response())
    mocker.patch.object(BaseClient, "get", get)
    mocker.patch.object(ComponentClient, "_sleep_interruptibly")

    with pytest.raises(RunCancelledError):
        _client(events, cancellation_token=cancel).put("infuse")

    assert _kinds(events) == ["started", "failed"]


def test_a_dry_run_reports_started_then_finished(events):
    _client(events, dry_run=True).put("infuse", volume="1 ml")

    assert _kinds(events) == ["started", "finished"]


def test_a_broken_observer_never_fails_the_command(mocker):
    mocker.patch.object(BaseClient, "put", return_value=_response())
    mocker.patch.object(BaseClient, "get", return_value=_response(b"true"))

    def broken(event: CommandEvent) -> None:
        raise RuntimeError("observer bug")

    client = ComponentClient(URL, component_ui=DEVICE, command_observer=broken)
    assert client.put("infuse") == {}


def test_without_an_observer_nothing_is_reported(mocker):
    mocker.patch.object(BaseClient, "put", return_value=_response())
    mocker.patch.object(BaseClient, "get", return_value=_response(b"true"))

    assert ComponentClient(URL, component_ui=DEVICE).put("infuse") == {}


# ── the executor names the node that sent the command ───────────────────────


class _Config(BaseModel):
    pass


def test_events_carry_the_node_that_sent_the_command(mocker, events):
    mocker.patch.object(BaseClient, "put", return_value=_response())
    mocker.patch.object(BaseClient, "get", return_value=_response(b"true"))
    client = _client(events)

    class DoseProcess(Process[_Config]):
        def build_workflow(self):
            graph = nx.DiGraph()
            for node in ("dose", "finish"):
                graph.add_node(
                    node,
                    **WorkflowNodeSpec(
                        node_id=node, method=node, label=node.title()
                    ).model_dump(exclude_none=True),
                )
            graph.add_edge(
                "dose",
                "finish",
                **WorkflowEdgeSpec(condition=True).model_dump(exclude_none=True),
            )
            return graph

        def dose(self, ctx: NodeExecutionContext) -> bool:
            client.put("infuse")
            return True

        def finish(self, ctx: NodeExecutionContext) -> bool:
            return True

    process = DoseProcess(config=_Config())
    WorkflowExecutor(compile_workflow(process.build_workflow())).execute(
        process, start_node="dose"
    )

    assert [event.node for event in events] == ["dose", "dose"]
    client.put("infuse")  # outside a run: no node
    assert events[-1].node is None
