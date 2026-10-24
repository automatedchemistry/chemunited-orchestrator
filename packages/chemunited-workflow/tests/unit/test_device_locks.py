"""Tests for the process-wide device lock (live platform view, step 1)."""

from __future__ import annotations

import json
import threading
import time

import pytest
import requests

from chemunited_workflow import device_locks
from chemunited_workflow.api.monitoring_store import MonitoringStore
from chemunited_workflow.api.services.monitoring import MonitoringService
from chemunited_workflow.clients import BaseClient, ComponentClient
from chemunited_workflow.device_locks import device_lock
from chemunited_workflow.exceptions import DeviceBusyError
from chemunited_workflow.monitoring_context import MonitoringContext
from chemunited_workflow.platform import Platform

# A name no other test uses: the lock registry is process-wide.
DEVICE = "lock-test-pump"
URL = f"http://device-server:8000/sim/{DEVICE}"


def _response(body: bytes = b"{}", status: int = 200) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response._content = body
    response.headers["Content-Type"] = "application/json"
    return response


@pytest.fixture(autouse=True)
def _short_lock_timeout(monkeypatch):
    monkeypatch.setattr(device_locks, "DEVICE_LOCK_TIMEOUT_SECONDS", 2.0)
    yield
    MonitoringContext.platform = None


def test_clients_with_the_same_component_name_share_one_lock():
    run_client = ComponentClient(URL, component_ui=DEVICE)
    monitor_client = ComponentClient(URL, component_ui=DEVICE)
    assert device_lock(run_client._device_key()) is device_lock(
        monitor_client._device_key()
    )


def test_unnamed_clients_are_keyed_by_their_url():
    assert (
        ComponentClient(URL)._device_key()
        != ComponentClient(f"{URL}/other")._device_key()
    )


def test_requests_to_one_device_never_overlap(mocker):
    in_put = threading.Event()
    release = threading.Event()
    order: list[str] = []

    def put(self, path, **kwargs):
        order.append("put-start")
        in_put.set()
        release.wait(2)
        order.append("put-end")
        return _response()

    def get(self, path, **kwargs):
        order.append(f"get-{path}")
        return _response(b"true" if path == "is-idle" else b"1.0")

    mocker.patch.object(BaseClient, "put", put)
    mocker.patch.object(BaseClient, "get", get)
    run_client = ComponentClient(URL, component_ui=DEVICE)
    monitor_client = ComponentClient(URL, component_ui=DEVICE)

    command = threading.Thread(target=lambda: run_client.put("infuse", volume="1 ml"))
    command.start()
    assert in_put.wait(2)
    readings: list[float] = []
    read = threading.Thread(target=lambda: readings.append(monitor_client.get("value")))
    read.start()
    time.sleep(0.1)
    assert readings == []  # waiting for the command's request to finish

    release.set()
    command.join(2)
    read.join(2)
    assert readings == [1.0]
    assert order.index("put-end") < order.index("get-value")


def test_monitoring_reads_get_through_during_a_long_idle_wait(mocker):
    polls = {"count": 0}

    def get(self, path, **kwargs):
        if path == "is-idle":
            polls["count"] += 1
            return _response(b"true" if polls["count"] >= 5 else b"false")
        return _response(b"1.0")

    mocker.patch.object(BaseClient, "put", lambda self, path, **kwargs: _response())
    mocker.patch.object(BaseClient, "get", get)
    run_client = ComponentClient(URL, component_ui=DEVICE, timeout_commands="30 s")
    mocker.patch.object(run_client, "_sleep_interruptibly", lambda _: time.sleep(0.05))
    monitor_client = ComponentClient(URL, component_ui=DEVICE)

    command = threading.Thread(target=lambda: run_client.put("infuse"))
    command.start()
    readings = []
    while command.is_alive():
        readings.append(monitor_client.get("value"))
        time.sleep(0.01)
    command.join()

    assert polls["count"] == 5
    assert len(readings) >= 3


def test_a_command_fails_with_device_busy_while_the_lock_is_held(monkeypatch, mocker):
    monkeypatch.setattr(device_locks, "DEVICE_LOCK_TIMEOUT_SECONDS", 0.05)
    mocker.patch.object(BaseClient, "put", lambda self, path, **kwargs: _response())
    mocker.patch.object(
        BaseClient, "get", lambda self, path, **kwargs: _response(b"true")
    )
    client = ComponentClient(URL, component_ui=DEVICE)

    lock = device_lock(DEVICE)
    lock.acquire()
    try:
        with pytest.raises(DeviceBusyError, match="busy"):
            client.put("infuse")
    finally:
        lock.release()

    client.put("infuse")  # usable again once the device is free


# ── monitoring skips a busy device ──────────────────────────────────────────


@pytest.fixture
def svc(tmp_path):
    (tmp_path / "connectivity").mkdir()
    (tmp_path / "connectivity" / "associations.json").write_text(
        json.dumps(
            {
                "server_url": "http://device-server:8000",
                "associations": [
                    {"component": DEVICE, "component_url": f"sim/{DEVICE}"}
                ],
            }
        ),
        encoding="utf-8",
    )
    return MonitoringService(project_dir=tmp_path, store=MonitoringStore())


def test_monitoring_skips_a_busy_device_instead_of_reporting_an_error(
    svc, monkeypatch, mocker
):
    monkeypatch.setattr(device_locks, "DEVICE_LOCK_TIMEOUT_SECONDS", 0.05)
    mocker.patch.object(
        BaseClient, "get", lambda self, path, **kwargs: _response(b"1.0")
    )
    platform = Platform.from_project_dir(svc._project_dir, error_resilient=True)

    lock = device_lock(DEVICE)
    lock.acquire()
    try:
        reading = svc._fetch_one(platform, DEVICE, "value", {})
    finally:
        lock.release()

    assert reading["skipped"] is True
    assert reading["error"] is None


def _wait_until(predicate, timeout=2.0, interval=0.01):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def test_a_skipped_tick_keeps_the_last_reading(svc, monkeypatch, mocker):
    monkeypatch.setattr(device_locks, "DEVICE_LOCK_TIMEOUT_SECONDS", 0.02)
    mocker.patch.object(
        BaseClient, "get", lambda self, path, **kwargs: _response(b"1.0")
    )
    close_spy = mocker.patch.object(BaseClient, "close")
    key = f"{DEVICE}::value"
    svc.write_config(
        {
            "sample_time": 0.03,
            "variables": [{"component": DEVICE, "command": "value", "kwargs": {}}],
        }
    )
    svc.start()
    try:
        assert _wait_until(lambda: key in svc.get_latest())
        lock = device_lock(DEVICE)
        lock.acquire()
        try:
            time.sleep(0.1)  # a reading fetched just before the lock lands first
            held = svc.get_latest()[key]
            time.sleep(0.2)  # several more ticks, all skipped
            assert svc.get_latest()[key] == held
            assert held["error"] is None
        finally:
            lock.release()
        assert _wait_until(lambda: svc.get_latest()[key]["tick"] > held["tick"])
    finally:
        svc.stop()
    assert _wait_until(lambda: close_spy.call_count >= 1)  # poll loop has exited
