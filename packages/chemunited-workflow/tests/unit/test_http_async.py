"""Mocked transport tests: no instrument or device server is contacted."""

import json
import threading
from concurrent.futures import Future

import pytest
import requests

from chemunited_workflow.background import (
    BackgroundCommandError,
    CommandOrigin,
    command_origin_scope,
)
from chemunited_workflow.clients.base import _pop_thread_resilient_errors
from chemunited_workflow.clients.http import BaseClient, ComponentClient
from chemunited_workflow.exceptions import RunCancelledError
from chemunited_workflow.platform import Platform


def response(body=None, status=200):
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps({} if body is None else body).encode()
    return result


def launch(fn):
    future = Future()

    def run():
        try:
            future.set_result(fn())
        except BaseException as exc:
            future.set_exception(exc)

    threading.Thread(target=run, daemon=True).start()
    return future


@pytest.fixture
def client(monkeypatch):
    value = ComponentClient("http://instrument.test/peltier", component_ui="Peltier")
    # Fail closed if a test forgets to install its fake transport.
    monkeypatch.setattr(
        value._session, "request", lambda *a, **k: pytest.fail("unexpected transport")
    )
    yield value
    if value._background is not None:
        value._background.close_commands(cancel=True)
    BaseClient.close(value)


def test_async_returns_before_http_response_and_preserves_submission_data(
    client, monkeypatch
):
    entered, release = threading.Event(), threading.Event()
    calls, events = [], []
    client._command_observer = events.append

    def transport(method, url, **kwargs):
        calls.append((method, url.rsplit("/", 1)[-1], kwargs))
        entered.set()
        assert release.wait(3)
        return response({"accepted": True})

    monkeypatch.setattr(client._session, "request", transport)
    params = {"temperature": "-20 degC"}
    try:
        with command_origin_scope(CommandOrigin("process_0", "cool", 0)):
            future = client.put_async("temperature", params=params)
        params["temperature"] = "100 degC"
        assert entered.wait(1)
        assert not future.done()
        release.set()
        assert future.result(1) == {"accepted": True}
        assert calls == [
            (
                "PUT",
                "temperature",
                {"params": {"temperature": "-20 degC"}, "json": None, "timeout": 30.0},
            )
        ]
        assert [event.kind for event in events] == ["started", "finished"]
        assert all(event.node == "cool" for event in events)
    finally:
        release.set()


def test_ordinary_put_still_blocks_and_forwards_wait_parameter(client, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    calls = []

    def transport(method, url, **kwargs):
        path = url.rsplit("/", 1)[-1]
        calls.append((path, kwargs))
        if path == "home":
            entered.set()
            assert release.wait(3)
        return response(True if path == "is-idle" else {})

    monkeypatch.setattr(client._session, "request", transport)
    call = launch(lambda: client.put("home", wait=True))
    try:
        assert entered.wait(1)
        assert not call.done()
        release.set()
        assert call.result(1) == {}
        assert calls[0][1]["params"] == {"wait": True}
        assert "timeout" not in calls[0][1]
        assert [path for path, _ in calls] == ["home", "is-idle"]
    finally:
        release.set()


def test_queue_orders_setpoints_and_ordinary_requests_with_per_call_completion(
    client, monkeypatch
):
    entered, release = threading.Event(), threading.Event()
    calls = []

    def transport(method, url, **kwargs):
        path = url.rsplit("/", 1)[-1]
        calls.append(path)
        if len(calls) == 1:
            entered.set()
            assert release.wait(3)
        return response(True if path == "is-idle" else {"ok": True})

    monkeypatch.setattr(client._session, "request", transport)
    first = client.put_async("first")
    assert entered.wait(1)
    second = client.put_async("second", wait_for_completion=True)
    ordinary = launch(lambda: client.get("temperature"))
    try:
        assert calls == ["first"] and not ordinary.done()
        release.set()
        first.result(1)
        second.result(1)
        ordinary.result(1)
        client.put("home", wait=True)
        assert calls == ["first", "second", "is-idle", "temperature", "home", "is-idle"]
        assert client._wait_for_completion is True
    finally:
        release.set()


def test_readiness_timeout_is_fatal_even_for_resilient_async_client(
    client, monkeypatch
):
    client._error_resilient = True
    client._feedback_timeout = 0
    monkeypatch.setattr(client._session, "request", lambda *a, **k: response(False))
    future = client.put_async("temperature", wait_for_completion=True)
    with pytest.raises(BackgroundCommandError) as caught:
        future.result(1)
    assert isinstance(caught.value.__cause__, TimeoutError)
    assert _pop_thread_resilient_errors() == []


def test_queued_synchronous_resilient_errors_return_to_caller_thread(
    client, monkeypatch
):
    client._error_resilient = True
    client._wait_for_completion = False

    def transport(method, url, **kwargs):
        result = response(status=500 if url.endswith("bad") else 200)
        client._raise_for_status(result)
        return result

    monkeypatch.setattr(client._session, "request", transport)
    client.put_async("activate").result(1)
    try:
        assert client.put("bad") == {}
        assert len(_pop_thread_resilient_errors()) == 1
        client._background.check_command_errors()
        assert client.put("good") == {}
    finally:
        _pop_thread_resilient_errors()


def test_platform_barrier_orders_acknowledgement_before_sensor_and_other_component_is_independent(
    client, monkeypatch
):
    entered, release = threading.Event(), threading.Event()
    other = ComponentClient("http://instrument.test/sensor", component_ui="TCdv4")
    platform = Platform({"Peltier": client, "TCdv4": other})

    def transport(*args, **kwargs):
        entered.set()
        assert release.wait(3)
        return response()

    monkeypatch.setattr(client._session, "request", transport)
    monkeypatch.setattr(other._session, "request", lambda *a, **k: response(20))
    client.put_async("temperature")
    assert entered.wait(1)
    barrier = launch(lambda: platform.wait_for_pending("Peltier"))
    try:
        assert other.get("temperature") == 20
        assert not barrier.done()
        release.set()
        barrier.result(1)
        platform.close_pending_commands()
    finally:
        release.set()
        platform.close_pending_commands(cancel=True)
        BaseClient.close(other)


def test_queued_http_timeout_and_raw_response(client, monkeypatch):
    calls = []
    result = response({"ok": True})

    def transport(*a, **kwargs):
        calls.append(kwargs)
        return result

    monkeypatch.setattr(client._session, "request", transport)
    assert client.put_async("temperature", raw_response=True).result(1) is result
    assert calls[0]["timeout"] == 30.0


def test_dry_async_never_uses_transport(client, monkeypatch):
    client._dry_run = True
    assert client.put_async("temperature", wait_for_completion=True).result(1) == {}


def test_queue_activation_waits_for_existing_inline_request(client, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    calls = []

    def transport(method, url, **kwargs):
        path = url.rsplit("/", 1)[-1]
        calls.append(path)
        if path == "existing":
            entered.set()
            assert release.wait(3)
        return response()

    client._wait_for_completion = False
    monkeypatch.setattr(client._session, "request", transport)
    existing = launch(lambda: client.put("existing"))
    assert entered.wait(1)
    submitted = client.put_async("queued")
    try:
        assert calls == ["existing"] and not submitted.done()
        release.set()
        existing.result(1)
        submitted.result(1)
        assert calls == ["existing", "queued"]
    finally:
        release.set()


def test_standalone_client_close_drains_and_is_idempotent(client, monkeypatch):
    entered, release = threading.Event(), threading.Event()

    def transport(*args, **kwargs):
        entered.set()
        assert release.wait(3)
        return response()

    monkeypatch.setattr(client._session, "request", transport)
    submitted = client.put_async("temperature")
    assert entered.wait(1)
    closing = launch(client.close)
    try:
        assert not closing.done()
        release.set()
        closing.result(1)
        assert submitted.result(1) == {}
        client.close()
        assert client._background.join(0) == []
    finally:
        release.set()


def test_cancellation_stops_idle_polling_and_queued_requests(client, monkeypatch):
    from chemunited_workflow.background import BackgroundTasks

    host = BackgroundTasks()
    client.bind_background_tasks(host)
    polled = threading.Event()

    def transport(method, url, **kwargs):
        if url.endswith("is-idle"):
            polled.set()
        return response(False)

    monkeypatch.setattr(client._session, "request", transport)
    running = client.put_async("temperature", wait_for_completion=True)
    assert polled.wait(1)
    queued = client.put_async("never")
    closing = launch(lambda: host.close_commands(cancel=True))
    closing.result(1)
    assert queued.cancelled()
    with pytest.raises(RunCancelledError):
        running.result(1)
    host.check_command_errors()
