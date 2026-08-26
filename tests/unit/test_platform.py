"""Unit tests for Platform (Step 01)."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from chemunited_workflow.clients import ComponentClient
from chemunited_workflow.exceptions import RunCancelledError
from chemunited_workflow.platform import Platform

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_missing_component_raises_key_error():
    p = Platform()
    with pytest.raises(KeyError, match="not registered"):
        p["missing"]


def test_key_error_lists_available():
    client = ComponentClient("http://server:8000/pump")
    p = Platform({"pump": client})
    with pytest.raises(KeyError, match="pump"):
        p["sensor"]


def test_register_and_contains():
    p = Platform()
    client = ComponentClient("http://server:8000/pump")
    p.register("pump", client)
    assert "pump" in p
    assert len(p) == 1


def test_mapping_api():
    c1 = ComponentClient("http://server:8000/a")
    c2 = ComponentClient("http://server:8000/b")
    p = Platform({"a": c1, "b": c2})
    assert set(p.keys()) == {"a", "b"}
    assert set(p.values()) == {c1, c2}
    assert len(p) == 2


def test_from_connectivity_loads_pump_skips_sensor():
    p = Platform.from_connectivity(FIXTURES / "associations.json")
    assert "pump" in p
    assert "sensor" not in p
    assert isinstance(p["pump"], ComponentClient)
    assert p["pump"].base_url == "http://device-server:8000/sim-ml600/pump"


def test_from_connectivity_passes_timeout_commands_to_clients():
    p = Platform.from_connectivity(
        FIXTURES / "associations.json",
        timeout_commands="5 s",
    )
    assert p["pump"].timeout_commands == "5 s"
    assert p["pump"]._feedback_timeout == 5.0


def test_from_connectivity_without_server_url_does_not_raise(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"associations": []}), encoding="utf-8")
    p = Platform.from_connectivity(bad)
    assert len(p) == 0


def test_from_connectivity_without_server_url_uses_component_url_as_is(tmp_path):
    path = tmp_path / "associations.json"
    path.write_text(
        json.dumps(
            {
                "associations": [
                    {
                        "component": "pump",
                        "component_url": "http://device-server:8000/sim-ml600/pump",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    p = Platform.from_connectivity(path)
    assert p["pump"].base_url == "http://device-server:8000/sim-ml600/pump"


def test_from_project_dir(tmp_path):
    conn_dir = tmp_path / "connectivity"
    conn_dir.mkdir()
    (conn_dir / "associations.json").write_text(
        (FIXTURES / "associations.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    p = Platform.from_project_dir(tmp_path)
    assert "pump" in p


# ── multi-protocol dispatch ───────────────────────────────────────────────────


def test_from_connectivity_dispatches_flowchem_sila2_opcua():
    from chemunited_workflow.clients import OpcUaComponentClient, SilaComponentClient

    p = Platform.from_connectivity(FIXTURES / "associations_multi_protocol.json")

    assert isinstance(p["pump"], ComponentClient)

    sila_client = p["sila-pump"]
    assert isinstance(sila_client, SilaComponentClient)
    assert sila_client._host == "192.168.1.50"
    assert sila_client._port == 50052

    opcua_client = p["opc-reactor"]
    assert isinstance(opcua_client, OpcUaComponentClient)
    assert opcua_client._endpoint == "opc.tcp://192.168.1.60:4840"
    assert opcua_client._root_node_id == "ns=2;s=Reactor1"
    assert opcua_client._idle_node_path == "2:Diagnostics/2:IsBusy"
    assert opcua_client._idle_value is False

    assert "unconfigured-sila" not in p


def test_from_connectivity_unknown_protocol_raises(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps(
            {
                "server_url": "http://device-server:8000",
                "associations": [{"component": "x", "protocol": "modbus"}],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="modbus"):
        Platform.from_connectivity(bad)


# ── Platform._wait ────────────────────────────────────────────────────────────


def test_wait_sleeps_without_cancellation_token():
    p = Platform()
    started = time.monotonic()
    p._wait(0.05)
    assert time.monotonic() - started >= 0.05


def test_wait_stops_when_cancelled():
    cancel_event = threading.Event()
    p = Platform(cancellation_token=cancel_event)

    timer = threading.Timer(0.05, cancel_event.set)
    started = time.monotonic()
    timer.start()
    try:
        with pytest.raises(RunCancelledError):
            p._wait(5.0)
    finally:
        timer.cancel()

    assert time.monotonic() - started < 1.0


def test_from_connectivity_stores_cancellation_token():
    cancel_event = threading.Event()
    p = Platform.from_connectivity(
        FIXTURES / "associations.json", cancellation_token=cancel_event
    )
    assert p._cancellation_token is cancel_event
