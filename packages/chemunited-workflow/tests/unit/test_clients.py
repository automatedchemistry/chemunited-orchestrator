"""Unit tests for BaseClient and ComponentClient (Step 01)."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass

import pytest
import requests
import responses as resp_lib

from chemunited_quantities import ChemUnitQuantity
from chemunited_workflow.clients import BaseClient, ComponentClient
from chemunited_workflow.durations import parse_timeout_commands
from chemunited_workflow.exceptions import (
    ConcurrentClientAccessError,
    RunCancelledError,
)

BASE_URL = "http://device-server:8000"


def _ok_json_response() -> requests.Response:
    response = requests.Response()
    response.status_code = 200
    response._content = b"{}"
    response.headers["Content-Type"] = "application/json"
    return response


def _idle_true_response() -> requests.Response:
    response = requests.Response()
    response.status_code = 200
    response._content = b"true"
    return response


# timeout_commands parsing


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("5 s", 5.0),
        ("2 min", 120.0),
        ("", None),
    ],
)
def test_parse_timeout_commands(value, expected):
    assert parse_timeout_commands(value) == expected


@pytest.mark.parametrize("value", ["invalid", "5 ml", "-1 s"])
def test_parse_timeout_commands_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        parse_timeout_commands(value)


# ── _build_url ────────────────────────────────────────────────────────────────


def test_build_url_trailing_slash_stripped():
    client = BaseClient("http://device-server:8000/")
    assert client._build_url("/pump/dose") == "http://device-server:8000/pump/dose"


def test_build_url_no_double_slash():
    client = BaseClient("http://device-server:8000")
    assert client._build_url("pump/dose") == "http://device-server:8000/pump/dose"


# ── close ─────────────────────────────────────────────────────────────────────


def test_close_closes_session(mocker):
    client = BaseClient(BASE_URL)
    close_spy = mocker.patch.object(client._session, "close")
    client.close()
    close_spy.assert_called_once()


# ── Hook order ────────────────────────────────────────────────────────────────


def test_hook_order_log_before_raise():
    client = BaseClient(BASE_URL)
    hooks = client._session.hooks["response"]
    names = [h.__name__ for h in hooks]
    assert names.index("_log_response") < names.index("_raise_for_status")


# ── _raise_for_status ─────────────────────────────────────────────────────────


@resp_lib.activate
def test_raise_for_status_on_4xx():
    resp_lib.add(resp_lib.GET, f"{BASE_URL}/x", status=404)
    client = BaseClient(BASE_URL)
    with pytest.raises(requests.HTTPError):
        client.get("/x")


@resp_lib.activate
def test_raise_for_status_on_5xx():
    resp_lib.add(resp_lib.GET, f"{BASE_URL}/x", status=500)
    client = BaseClient(BASE_URL)
    with pytest.raises(requests.HTTPError):
        client.get("/x")


@resp_lib.activate
def test_200_does_not_raise():
    resp_lib.add(resp_lib.GET, f"{BASE_URL}/x", status=200, body=b"ok")
    client = BaseClient(BASE_URL)
    r = client.get("/x")
    assert r.status_code == 200


# ── _log_response ─────────────────────────────────────────────────────────────


@resp_lib.activate
def test_log_response_called_on_success(caplog):
    resp_lib.add(resp_lib.PUT, f"{BASE_URL}/dose", status=200, body=b"")
    client = BaseClient(BASE_URL)
    import logging

    with caplog.at_level(logging.DEBUG):
        client.put("/dose", json={"volume_ml": 5.0})
    # No assertion on exact log text — just verify no exception raised


# ── ComponentClient: sequential calls ────────────────────────────────────────


@resp_lib.activate
def test_component_client_sequential_calls_succeed():
    resp_lib.add(resp_lib.GET, f"{BASE_URL}/x", status=200, body=b"")
    resp_lib.add(resp_lib.GET, f"{BASE_URL}/x", status=200, body=b"")
    client = ComponentClient(BASE_URL)
    r1 = client.get("/x", raw_response=True)
    r2 = client.get("/x", raw_response=True)
    assert r1.status_code == 200
    assert r2.status_code == 200


# ── ComponentClient: raw_response toggle ─────────────────────────────────────


@resp_lib.activate
@pytest.mark.parametrize(
    ("method", "verb"),
    [(resp_lib.GET, "get"), (resp_lib.PUT, "put"), (resp_lib.POST, "post")],
)
def test_component_client_defaults_to_parsed_json(method, verb):
    resp_lib.add(method, f"{BASE_URL}/x", status=200, json={"ready": True})
    if verb in ("put", "post"):
        resp_lib.add(resp_lib.GET, f"{BASE_URL}/is-idle", status=200, body=b"true")
    client = ComponentClient(BASE_URL)
    result = getattr(client, verb)("/x")
    assert result == {"ready": True}


@resp_lib.activate
@pytest.mark.parametrize(
    ("method", "verb"),
    [(resp_lib.GET, "get"), (resp_lib.PUT, "put"), (resp_lib.POST, "post")],
)
def test_component_client_raw_response_returns_response_object(method, verb):
    resp_lib.add(method, f"{BASE_URL}/x", status=200, json={"ready": True})
    if verb in ("put", "post"):
        resp_lib.add(resp_lib.GET, f"{BASE_URL}/is-idle", status=200, body=b"true")
    client = ComponentClient(BASE_URL)
    result = getattr(client, verb)("/x", raw_response=True)
    assert isinstance(result, requests.Response)
    assert result.status_code == 200


# ── automatic wait-for-idle (GET /is-idle) ───────────────────────────────────


def test_put_waits_for_is_idle_before_returning(mocker):
    answers = iter(["false", "false", "true"])
    calls = []

    def fake_get(self, path):
        calls.append(path)
        response = requests.Response()
        response.status_code = 200
        response._content = next(answers).encode()
        return response

    mocker.patch.object(BaseClient, "get", new=fake_get)
    mocker.patch.object(BaseClient, "put", return_value=_ok_json_response())

    client = ComponentClient(BASE_URL, timeout_commands="")
    client.put("/dose", volume=5)

    assert calls == ["is-idle", "is-idle", "is-idle"]


def test_get_does_not_poll_is_idle(mocker):
    calls = []

    def fake_get(self, path, **kwargs):
        calls.append(path)
        response = requests.Response()
        response.status_code = 200
        response._content = b"{}"
        response.headers["Content-Type"] = "application/json"
        return response

    mocker.patch.object(BaseClient, "get", new=fake_get)

    client = ComponentClient(BASE_URL)
    client.get("/position")

    assert calls == ["/position"]


def test_missing_is_idle_endpoint_warns_once_and_does_not_block(mocker):
    idle_response = requests.Response()
    idle_response.status_code = 404
    idle_response._content = b"Not Found"
    mocker.patch.object(BaseClient, "get", return_value=idle_response)
    mocker.patch.object(BaseClient, "put", return_value=_ok_json_response())
    warning_spy = mocker.patch("chemunited_workflow.clients.http.logger.warning")

    client = ComponentClient(BASE_URL)
    client.put("/dose", volume=5)
    client.put("/dose", volume=5)

    assert warning_spy.call_count == 1
    assert client._is_idle_supported is False


def test_is_idle_timeout_raises(mocker):
    idle_response = requests.Response()
    idle_response.status_code = 200
    idle_response._content = b"false"
    mocker.patch.object(BaseClient, "get", return_value=idle_response)
    mocker.patch.object(BaseClient, "put", return_value=_ok_json_response())
    mocker.patch.object(ComponentClient, "_sleep_interruptibly")

    client = ComponentClient(BASE_URL, timeout_commands="0.01 s")
    with pytest.raises(TimeoutError, match="0.01"):
        client.put("/dose")


def test_is_idle_timeout_pushed_when_error_resilient(mocker):
    idle_response = requests.Response()
    idle_response.status_code = 200
    idle_response._content = b"false"
    mocker.patch.object(BaseClient, "get", return_value=idle_response)
    mocker.patch.object(BaseClient, "put", return_value=_ok_json_response())
    mocker.patch.object(ComponentClient, "_sleep_interruptibly")

    client = ComponentClient(BASE_URL, timeout_commands="0.01 s", error_resilient=True)
    client.put("/dose")  # does not raise


def test_is_idle_polling_stops_when_cancelled(mocker):
    response = requests.Response()
    response.status_code = 200
    response._content = b"false"
    mocker.patch.object(BaseClient, "get", return_value=response)
    mocker.patch.object(BaseClient, "put", return_value=_ok_json_response())

    cancel_event = threading.Event()
    client = ComponentClient(
        BASE_URL,
        timeout_commands="",
        cancellation_token=cancel_event,
    )

    timer = threading.Timer(0.05, cancel_event.set)
    started = time.monotonic()
    timer.start()
    try:
        with pytest.raises(RunCancelledError):
            client.put("/dose")
    finally:
        timer.cancel()

    assert time.monotonic() - started < 1.0


def test_call_blocks_while_paused_then_proceeds(mocker):
    """Mid-node granularity: a call holds at the pause checkpoint, not just
    between nodes, and continues once resumed."""
    response = requests.Response()
    response.status_code = 200
    response._content = b"true"
    mocker.patch.object(BaseClient, "get", return_value=response)

    pause_event = threading.Event()
    pause_event.set()
    client = ComponentClient(BASE_URL, timeout_commands="", pause_event=pause_event)

    timer = threading.Timer(0.05, pause_event.clear)
    started = time.monotonic()
    timer.start()
    try:
        client.get("/x", raw_response=True)
    finally:
        timer.cancel()

    assert time.monotonic() - started >= 0.05


def test_call_cancelled_while_paused_raises_and_unblocks(mocker):
    mocker.patch.object(BaseClient, "get", return_value=_ok_json_response())

    pause_event = threading.Event()
    pause_event.set()
    cancel_event = threading.Event()
    client = ComponentClient(
        BASE_URL,
        timeout_commands="",
        cancellation_token=cancel_event,
        pause_event=pause_event,
    )

    timer = threading.Timer(0.05, cancel_event.set)
    started = time.monotonic()
    timer.start()
    try:
        with pytest.raises(RunCancelledError):
            client.get("/x", raw_response=True)
    finally:
        timer.cancel()

    assert time.monotonic() - started < 1.0


def test_dry_run_put_does_not_poll_is_idle(mocker):
    get_spy = mocker.patch.object(BaseClient, "get")

    client = ComponentClient(BASE_URL, dry_run=True)
    client.put("/dose", volume=5)

    get_spy.assert_not_called()


# ── stale execution-option kwargs from older process files ──────────────────


def test_stale_wait_kwargs_do_not_crash_and_become_query_params(mocker):
    """Old process files may still pass wait_time/wait_feedback_status/etc.

    These are no longer recognized keyword arguments — they fall through to
    ``**command_params`` and are sent as harmless, unused query parameters
    instead of raising a TypeError.
    """
    captured: dict[str, object] = {}

    def fake_put(self, path, *, params=None, json=None, **kwargs):
        captured["params"] = params
        response = requests.Response()
        response.status_code = 200
        response._content = b"{}"
        response.headers["Content-Type"] = "application/json"
        return response

    def fake_get(self, path, **kwargs):
        response = requests.Response()
        response.status_code = 200
        response._content = b"true"
        return response

    mocker.patch.object(BaseClient, "put", new=fake_put)
    mocker.patch.object(BaseClient, "get", new=fake_get)

    client = ComponentClient(BASE_URL)
    client.put(
        "/dose",
        volume=5,
        wait_time=2,
        wait_feedback_status=True,
        feedback_status_command="is-pumping",
        feedback_answer="false",
    )

    assert captured["params"]["wait_time"] == 2
    assert captured["params"]["feedback_status_command"] == "is-pumping"


# ── ComponentClient: concurrency guard ───────────────────────────────────────


def test_concurrent_access_raises():
    """While one thread holds the lock, a second raises ConcurrentClientAccessError."""
    client = ComponentClient(BASE_URL)
    errors: list[Exception] = []

    # Hold the lock from the main thread to simulate a concurrent access
    client._access_lock.acquire()
    try:

        def attempt():
            try:
                client.get("/x")
            except ConcurrentClientAccessError as exc:
                errors.append(exc)

        t = threading.Thread(target=attempt)
        t.start()
        t.join(timeout=2.0)
        assert not t.is_alive(), "thread hung — lock was not detected"
    finally:
        client._access_lock.release()

    assert len(errors) == 1
    assert "simultaneously" in str(errors[0])


def test_concurrent_error_message_contains_url():
    client = ComponentClient("http://my-device:9000/pump")
    # Force the lock to appear held
    client._access_lock.acquire()
    try:
        with pytest.raises(ConcurrentClientAccessError) as exc_info:
            client.get("/dose")
        assert "http://my-device:9000/pump" in str(exc_info.value)
    finally:
        client._access_lock.release()


def test_client_usable_after_failed_concurrent_call():
    """Lock must be released even when a concurrent-access error is raised."""
    client = ComponentClient(BASE_URL)
    client._access_lock.acquire()
    try:
        with pytest.raises(ConcurrentClientAccessError):
            client.get("/x")
    finally:
        client._access_lock.release()

    # After releasing the lock, the client should work normally
    with resp_lib.RequestsMock() as rsps:
        rsps.add(resp_lib.GET, f"{BASE_URL}/x", status=200, body=b"")
        r = client.get("/x", raw_response=True)
    assert r.status_code == 200


# ── _write_json_log ───────────────────────────────────────────────────────────


def test_write_json_log_none_creates_no_file(tmp_path):
    client = ComponentClient(BASE_URL, pool_json_log=None)
    client._write_json_log(
        {"method": "GET", "command": "/x", "component": "pump", "params": None}
    )
    assert list(tmp_path.iterdir()) == []


def test_write_json_log_writes_expected_keys(tmp_path):
    log_path = tmp_path / "pump.jsonl"
    client = ComponentClient(BASE_URL, pool_json_log=log_path)
    client._write_json_log(
        {
            "method": "PUT",
            "command": "/dose",
            "component": "pump",
            "params": {"volume": 5},
        }
    )
    record = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert record["method"] == "PUT"
    assert record["command"] == "/dose"
    assert record["component"] == "pump"
    assert record["params"] == {"volume": 5}


def test_write_json_log_appends_multiple_lines(tmp_path):
    log_path = tmp_path / "pump.jsonl"
    client = ComponentClient(BASE_URL, pool_json_log=log_path)
    client._write_json_log(
        {"method": "PUT", "command": "/a", "component": "pump", "params": None}
    )
    client._write_json_log(
        {"method": "GET", "command": "/b", "component": "pump", "params": None}
    )
    lines = [
        line
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(lines) == 2
    assert json.loads(lines[0])["command"] == "/a"
    assert json.loads(lines[1])["command"] == "/b"


def test_write_json_log_creates_parent_dir(tmp_path):
    log_path = tmp_path / "nested" / "deep" / "pump.jsonl"
    client = ComponentClient(BASE_URL, pool_json_log=log_path)
    client._write_json_log(
        {"method": "GET", "command": "/x", "component": "pump", "params": None}
    )
    assert log_path.exists()


def test_write_json_log_called_before_request_dry_run(tmp_path):
    log_path = tmp_path / "pump.jsonl"
    client = ComponentClient(BASE_URL, dry_run=True, pool_json_log=log_path)
    client.get("/x")
    assert log_path.exists()


def test_write_json_log_written_in_dry_run(tmp_path):
    log_path = tmp_path / "pump.jsonl"
    client = ComponentClient(BASE_URL, dry_run=True, pool_json_log=log_path)
    client.put("/dose", volume=3)
    record = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert record["method"] == "PUT"
    assert record["command"] == "/dose"


def test_write_json_log_with_quantity_params_writes_valid_jsonl(tmp_path):
    log_path = tmp_path / "pump.jsonl"
    client = ComponentClient(BASE_URL, pool_json_log=log_path)

    client._write_json_log(
        {
            "method": "PUT",
            "command": "/withdraw",
            "component": "pump",
            "params": {
                "volume": ChemUnitQuantity(1, "ml"),
                "rate": ChemUnitQuantity(2.0, "ml/min"),
            },
        }
    )

    record = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert record["params"] == {
        "volume": "1 milliliter",
        "rate": "2.0 milliliter / minute",
    }


def test_component_client_put_dry_run_accepts_quantity_params():
    client = ComponentClient(BASE_URL, dry_run=True)

    response = client.put(
        "/withdraw",
        raw_response=True,
        rate="4 ml/min",
        volume=ChemUnitQuantity(1, "ml"),
    )

    assert response.status_code == 200


def test_component_client_put_normalizes_nested_quantity_params(tmp_path):
    @dataclass
    class CommandMetadata:
        path: object
        target: object

    log_path = tmp_path / "pump.jsonl"
    client = ComponentClient(BASE_URL, dry_run=True, pool_json_log=log_path)

    client.put(
        "/withdraw",
        recipe={
            "steps": [
                {"volume": ChemUnitQuantity(1, "ml")},
                {"rate": ChemUnitQuantity(2.0, "ml/min")},
            ],
            "metadata": CommandMetadata(
                path=tmp_path / "recipe.json",
                target=ChemUnitQuantity(3, "ml"),
            ),
        },
    )

    record = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert record["params"]["recipe"] == {
        "steps": [
            {"volume": "1 milliliter"},
            {"rate": "2.0 milliliter / minute"},
        ],
        "metadata": {
            "path": str(tmp_path / "recipe.json"),
            "target": "3 milliliter",
        },
    }


def test_component_client_put_passes_safe_params_to_base_client(mocker):
    captured: dict[str, object] = {}

    def fake_put(self, path, *, params=None, json=None, **kwargs):
        captured["params"] = params
        captured["json"] = json
        response = requests.Response()
        response.status_code = 200
        return response

    mocker.patch.object(BaseClient, "put", new=fake_put)
    mocker.patch.object(BaseClient, "get", return_value=_idle_true_response())
    client = ComponentClient(BASE_URL)

    client.put(
        "/withdraw",
        raw_response=True,
        params={"volume": ChemUnitQuantity(1, "ml")},
        json={"rate": ChemUnitQuantity(2.0, "ml/min")},
    )

    assert captured["params"] == {"volume": "1 milliliter"}


# ── discover_commands ─────────────────────────────────────────────────────────

_FAKE_OPENAPI_SCHEMA = {
    "paths": {
        "/sim/pump/infuse": {
            "put": {
                "summary": "Infuse",
                "parameters": [
                    {
                        "name": "rate",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "string", "default": "1 ml/min"},
                    }
                ],
            }
        },
        "/sim/pump/is-reachable": {
            "get": {"summary": "Is Reachable", "parameters": []}
        },
        "/sim/pump/user-data": {
            "put": {
                "summary": "User Data",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"type": "object"},
                        }
                    },
                },
            }
        },
        "/sim/pump/position": {
            "get": {"summary": "Get Position", "parameters": []},
            "put": {"summary": "Set Position", "parameters": []},
        },
        "/sim/other/position": {"get": {"summary": "Position", "parameters": []}},
    }
}


@resp_lib.activate
def test_discover_commands_includes_get_and_put():
    resp_lib.add(
        resp_lib.GET, f"{BASE_URL}/openapi.json", json=_FAKE_OPENAPI_SCHEMA, status=200
    )
    client = ComponentClient(f"{BASE_URL}/sim/pump")
    commands = client.discover_commands()

    assert commands["infuse_put"]["type"] == "put"
    assert commands["is-reachable_get"]["type"] == "get"
    assert "position" not in commands


@resp_lib.activate
def test_discover_commands_same_path_get_and_put_both_kept():
    resp_lib.add(
        resp_lib.GET, f"{BASE_URL}/openapi.json", json=_FAKE_OPENAPI_SCHEMA, status=200
    )
    client = ComponentClient(f"{BASE_URL}/sim/pump")
    commands = client.discover_commands()

    assert commands["position_get"] == {
        "name": "position",
        "type": "get",
        "parameters": {},
    }
    assert commands["position_put"] == {
        "name": "position",
        "type": "put",
        "parameters": {},
    }


@resp_lib.activate
def test_discover_commands_query_parameter_shape():
    resp_lib.add(
        resp_lib.GET, f"{BASE_URL}/openapi.json", json=_FAKE_OPENAPI_SCHEMA, status=200
    )
    client = ComponentClient(f"{BASE_URL}/sim/pump")
    commands = client.discover_commands()

    assert commands["infuse_put"]["parameters"] == {
        "rate": {
            "in": "query",
            "required": False,
            "type": "string",
            "default": "1 ml/min",
        }
    }
    assert commands["is-reachable_get"]["parameters"] == {}


@resp_lib.activate
def test_discover_commands_request_body_becomes_body_parameter():
    resp_lib.add(
        resp_lib.GET, f"{BASE_URL}/openapi.json", json=_FAKE_OPENAPI_SCHEMA, status=200
    )
    client = ComponentClient(f"{BASE_URL}/sim/pump")
    commands = client.discover_commands()

    assert commands["user-data_put"]["parameters"] == {
        "body": {"in": "body", "required": True, "type": "object"}
    }
