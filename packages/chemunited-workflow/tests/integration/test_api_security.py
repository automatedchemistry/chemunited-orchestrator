"""Integration tests for AccessControlMiddleware (loopback-or-token gate)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from tests.helpers import LOOPBACK_CLIENT

from chemunited_workflow.api import create_api

REMOTE_CLIENT_V6 = ("::1", 51216)


def test_safe_method_open_from_remote_without_token():
    client = TestClient(create_api())
    r = client.get("/run/active")
    assert r.status_code == 200


def test_unsafe_method_blocked_from_remote_without_token():
    client = TestClient(create_api())
    r = client.put("/project/", json={"project_dir": "."})
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


def test_unsafe_method_allowed_from_loopback_v4():
    client = TestClient(create_api(), client=LOOPBACK_CLIENT)
    r = client.put("/project/", json={"project_dir": "does-not-exist"})
    assert r.status_code != 401


def test_unsafe_method_allowed_from_loopback_v6():
    client = TestClient(create_api(), client=REMOTE_CLIENT_V6)
    r = client.put("/project/", json={"project_dir": "does-not-exist"})
    assert r.status_code != 401


def test_unsafe_method_blocked_with_wrong_token():
    client = TestClient(create_api(token="secret"))
    r = client.put(
        "/project/",
        json={"project_dir": "."},
        headers={"Authorization": "Bearer wrong"},
    )
    assert r.status_code == 401


def test_unsafe_method_allowed_with_correct_token():
    client = TestClient(create_api(token="secret"))
    r = client.put(
        "/project/",
        json={"project_dir": "does-not-exist"},
        headers={"Authorization": "Bearer secret"},
    )
    assert r.status_code != 401


def test_missing_authorization_header_blocked_with_token_configured():
    client = TestClient(create_api(token="secret"))
    r = client.post("/run/", json={"protocol": "x"})
    assert r.status_code == 401


def test_malformed_authorization_header_blocked():
    client = TestClient(create_api(token="secret"))
    r = client.post(
        "/run/", json={"protocol": "x"}, headers={"Authorization": "Basic abc123"}
    )
    assert r.status_code == 401

    r = client.post(
        "/run/", json={"protocol": "x"}, headers={"Authorization": "Bearer "}
    )
    assert r.status_code == 401


def test_sse_stream_unaffected_by_gate():
    client = TestClient(create_api())
    r = client.get("/run/stream")
    assert r.status_code != 401


def test_options_is_safe_method():
    client = TestClient(create_api())
    r = client.options("/run/")
    assert r.status_code != 401
