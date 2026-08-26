"""Unit tests for ProtocolService — Step 07 additions."""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Annotated
from unittest.mock import MagicMock, patch

import pytest
import requests
import responses as resp_lib
from pydantic import AliasChoices, BaseModel, Field
from pydantic.json_schema import PydanticJsonSchemaWarning

from chemunited_quantities import ChemQuantityValidator, ChemUnitQuantity
from chemunited_workflow.api.services.protocol import ProtocolService

_MODULE = "chemunited_workflow.api.services.protocol._requests"
FlowRate = Annotated[ChemUnitQuantity, ChemQuantityValidator("ml/min")]


@pytest.fixture
def svc(tmp_path):
    (tmp_path / "protocols").mkdir()
    (tmp_path / "protocols_historic").mkdir()
    (tmp_path / "log").mkdir()
    (tmp_path / "connectivity").mkdir()

    assoc = {
        "server_url": "http://device-server:8000",
        "associations": [
            {"component": "pump", "component_url": "sim/pump"},
            {"component": "valve", "component_url": "sim/valve"},
            {"component": "empty", "component_url": ""},
            {
                "component": "sila-pump",
                "protocol": "sila2",
                "sila_host": "localhost",
                "sila_port": 50999,
                "sila_insecure": True,
            },
            {"component": "unconfigured-sila", "protocol": "sila2"},
            {
                "component": "opc-valve",
                "protocol": "opcua",
                "opcua_endpoint": "opc.tcp://localhost:4999",
                "opcua_node_id": "ns=2;s=Root",
            },
            {"component": "unconfigured-opcua", "protocol": "opcua"},
        ],
    }
    (tmp_path / "connectivity" / "associations.json").write_text(
        json.dumps(assoc), encoding="utf-8"
    )

    class FakeMain(BaseModel):
        x: float = 1.0

    return ProtocolService(
        project_dir=tmp_path,
        processes={},
        configs={},
        main_parameter_class=FakeMain,
    )


@pytest.fixture(autouse=True)
def _no_real_device_connections(mocker):
    """Safety net: `svc`'s associations.json includes sila2/opcua entries pointing
    at hosts that don't exist. Without this, any test touching every configured
    component (e.g. ping_components) would attempt a real, slow/hanging network
    connection. Tests that want real sila2/opcua behavior patch these same targets
    again with their own fakes further down in the test body — a later patch on
    the same target takes precedence for the duration of that test.
    """
    mocker.patch(
        "chemunited_workflow.clients.sila.SilaClient",
        side_effect=ConnectionError("test-mock: no real sila2 server configured"),
    )
    mocker.patch(
        "chemunited_workflow.clients.opcua.Client",
        side_effect=ConnectionError("test-mock: no real opcua server configured"),
    )


# ── Process schema generation ─────────────────────────────────────────────────


def _schema_service(tmp_path, factory_calls=None):
    def make_values():
        if factory_calls is not None:
            factory_calls.append("called")
        return ["generated"]

    class FakeConfig(BaseModel):
        rate: FlowRate = ChemUnitQuantity("0.1 ml/min")
        label: str = "pump"
        count: int = 3
        enabled: bool = False
        note: str | None = None
        required_value: float
        generated: list[str] = Field(default_factory=make_values)
        internal_rate: FlowRate = Field(
            default=ChemUnitQuantity("0.2 ml/min"),
            validation_alias=AliasChoices("flowRate", "flow_rate"),
        )

    class FakeMain(BaseModel):
        main_rate: FlowRate = ChemUnitQuantity("0.3 ml/min")

    class FakeProcess:
        """Fake process."""

    return ProtocolService(
        project_dir=tmp_path,
        processes={"fake": FakeProcess},
        configs={"fake": FakeConfig},
        main_parameter_class=FakeMain,
    )


def test_list_processes_serializes_typed_defaults(tmp_path):
    schema = _schema_service(tmp_path).list_processes()[0]["config_schema"]
    properties = schema["properties"]

    assert properties["rate"]["default"] == "0.1 milliliter / minute"
    assert properties["label"]["default"] == "pump"
    assert properties["count"]["default"] == 3
    assert properties["enabled"]["default"] is False
    assert properties["note"]["default"] is None
    assert "default" not in properties["required_value"]


def test_schema_generation_skips_default_factories(tmp_path):
    factory_calls = []
    schema = _schema_service(tmp_path, factory_calls).list_processes()[0][
        "config_schema"
    ]

    assert factory_calls == []
    assert "default" not in schema["properties"]["generated"]


def test_schema_generation_uses_validation_alias(tmp_path):
    schema = _schema_service(tmp_path).list_processes()[0]["config_schema"]

    assert schema["properties"]["flowRate"]["default"] == ("0.2 milliliter / minute")


def test_get_process_schema_serializes_config_and_main_defaults(tmp_path):
    result = _schema_service(tmp_path).get_process_schema("fake")

    assert result["config_schema"]["properties"]["rate"]["default"] == (
        "0.1 milliliter / minute"
    )
    assert (
        result["main_parameter_schema"]["properties"]["main_rate"]["default"]
        == "0.3 milliliter / minute"
    )


def test_schema_generation_suppresses_non_serializable_default_warning(tmp_path):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        service = _schema_service(tmp_path)
        service.list_processes()
        service.get_process_schema("fake")

    assert not any(
        isinstance(item.message, PydanticJsonSchemaWarning) for item in caught
    )


# ── read_process ──────────────────────────────────────────────────────────────


def test_read_process_valid(svc, tmp_path):
    (tmp_path / "protocols" / "clean.py").write_text(
        "class MyProcess:\n    pass\n", encoding="utf-8"
    )
    source = svc.read_process("clean")
    assert "class MyProcess" in source


def test_read_process_path_traversal(svc):
    with pytest.raises(ValueError, match="path traversal"):
        svc.read_process("../connectivity/associations")


def test_read_process_not_found(svc):
    with pytest.raises(FileNotFoundError):
        svc.read_process("ghost")


# ── write_protocol name validation ────────────────────────────────────────────


def test_write_protocol_rejects_empty_name(svc):
    with pytest.raises(ValueError, match="empty"):
        svc.write_protocol("", {})


def test_write_protocol_rejects_whitespace_only_name(svc):
    with pytest.raises(ValueError, match="empty"):
        svc.write_protocol("   ", {})


@pytest.mark.parametrize("bad_char", ["/", "\\", ":", "?", "#", "*", "<", ">", "|"])
def test_write_protocol_rejects_invalid_chars(svc, bad_char):
    with pytest.raises(ValueError, match="invalid characters"):
        svc.write_protocol(f"my{bad_char}protocol", {})


# ── delete_protocol ───────────────────────────────────────────────────────────


def test_delete_protocol_existing(svc, tmp_path):
    snap = tmp_path / "protocols_historic" / "snap_001.json"
    snap.write_text("{}", encoding="utf-8")
    result = svc.delete_protocol("snap_001.json")
    assert result is None


def test_delete_protocol_missing(svc):
    with pytest.raises(FileNotFoundError):
        svc.delete_protocol("missing.json")


def test_delete_protocol_file_gone_after_call(svc, tmp_path):
    snap = tmp_path / "protocols_historic" / "snap_002.json"
    snap.write_text("{}", encoding="utf-8")
    svc.delete_protocol("snap_002.json")
    assert not snap.exists()


# ── search_logs ───────────────────────────────────────────────────────────────


def test_search_logs_match_found(svc, tmp_path):
    (tmp_path / "log" / "test.log").write_text(
        "2026-05-15 INFO process started\n2026-05-15 INFO process finished\n",
        encoding="utf-8",
    )
    results = svc.search_logs("started")
    assert len(results) == 1
    assert results[0]["filename"] == "test.log"
    assert results[0]["line_number"] == 1
    assert "started" in results[0]["line"]


def test_search_logs_no_match(svc, tmp_path):
    (tmp_path / "log" / "test2.log").write_text("nothing here\n", encoding="utf-8")
    assert svc.search_logs("zzznomatch") == []


def test_search_logs_case_insensitive(svc, tmp_path):
    (tmp_path / "log" / "test3.log").write_text(
        "2026 ERROR occurred\n", encoding="utf-8"
    )
    results = svc.search_logs("error")
    assert len(results) == 1


def test_search_logs_max_results(svc, tmp_path):
    (tmp_path / "log" / "multi.log").write_text(
        "\n".join(f"line {i}" for i in range(5)), encoding="utf-8"
    )
    results = svc.search_logs("line", max_results=2)
    assert len(results) == 2


def test_search_logs_invalid_utf8(svc, tmp_path):
    (tmp_path / "log" / "binary.log").write_bytes(b"valid line\n\xff\xfe bad bytes\n")
    results = svc.search_logs("valid")
    assert any(r["filename"] == "binary.log" for r in results)


def test_search_logs_file_disappears(svc, tmp_path):
    log_file = tmp_path / "log" / "vanish.log"
    log_file.write_text("content\n", encoding="utf-8")

    original = Path.read_text

    def patched(self, *args, **kwargs):
        if self == log_file:
            raise OSError("file gone")
        return original(self, *args, **kwargs)

    with patch.object(Path, "read_text", patched):
        results = svc.search_logs("content")

    assert isinstance(results, list)


# ── ping_components ───────────────────────────────────────────────────────────


def _mock_response(status_code: int, elapsed_ms: float = 100.0) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.elapsed.total_seconds.return_value = elapsed_ms / 1000.0
    return resp


def test_ping_online_200(svc):
    with patch(f"{_MODULE}.get", return_value=_mock_response(200)):
        results = svc.ping_components()
    named = {r["component"]: r for r in results}
    assert named["pump"]["online"] is True
    assert named["pump"]["status_code"] == 200
    assert isinstance(named["pump"]["latency_ms"], int)


def test_ping_online_503(svc):
    with patch(f"{_MODULE}.get", return_value=_mock_response(503)):
        results = svc.ping_components()
    named = {r["component"]: r for r in results}
    assert named["valve"]["online"] is True
    assert named["valve"]["status_code"] == 503


def test_ping_connection_error(svc):
    with patch(
        f"{_MODULE}.get", side_effect=requests.exceptions.ConnectionError("refused")
    ):
        results = svc.ping_components()
    named = {r["component"]: r for r in results}
    for name in ("pump", "valve"):
        assert named[name]["online"] is False
        assert named[name]["error"].startswith("ConnectionError")


def test_ping_timeout(svc):
    with patch(f"{_MODULE}.get", side_effect=requests.exceptions.Timeout()):
        results = svc.ping_components()
    named = {r["component"]: r for r in results}
    for name in ("pump", "valve"):
        assert named[name]["online"] is False
        assert named[name]["error"].startswith("Timeout")


def test_ping_empty_url_skipped(svc):
    with patch(f"{_MODULE}.get", return_value=_mock_response(200)):
        results = svc.ping_components()
    components = [r["component"] for r in results]
    assert "empty" not in components


def test_ping_two_valid_devices(svc):
    with patch(f"{_MODULE}.get", return_value=_mock_response(200)):
        results = svc.ping_components()
    components = [r["component"] for r in results]
    assert "pump" in components
    assert "valve" in components
    # sila-pump/opc-valve are also configured and pingable (protocol-agnostic);
    # unconfigured-sila/unconfigured-opcua/empty are skipped, same as flowchem.
    assert "sila-pump" in components
    assert "opc-valve" in components
    assert "unconfigured-sila" not in components
    assert "unconfigured-opcua" not in components
    assert len(results) == 4


# ── is-reachable probe ──────────────────────────────────────────────────────


def _reachability_response(status_code: int, value: str | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.ok = 200 <= status_code < 300
    if value is not None:
        resp.json.return_value = value
    return resp


def test_ping_reachability_online(svc):
    reach_resp = _reachability_response(200, "online")
    with patch(
        f"{_MODULE}.get",
        side_effect=[_mock_response(200), reach_resp, _mock_response(200), reach_resp],
    ):
        results = svc.ping_components()
    named = {r["component"]: r for r in results}
    assert named["pump"]["reachability"] == "online"
    assert named["pump"]["reachability_supported"] is True


def test_ping_reachability_not_supported_404(svc):
    reach_resp = _reachability_response(404)
    with patch(
        f"{_MODULE}.get",
        side_effect=[_mock_response(200), reach_resp, _mock_response(200), reach_resp],
    ):
        results = svc.ping_components()
    named = {r["component"]: r for r in results}
    assert named["pump"]["reachability"] is None
    assert named["pump"]["reachability_supported"] is False


def test_ping_reachability_undetermined_on_error(svc):
    with patch(
        f"{_MODULE}.get",
        side_effect=[
            _mock_response(200),
            requests.exceptions.Timeout(),
            _mock_response(200),
            requests.exceptions.Timeout(),
        ],
    ):
        results = svc.ping_components()
    named = {r["component"]: r for r in results}
    assert named["pump"]["online"] is True
    assert named["pump"]["reachability"] is None
    assert named["pump"]["reachability_supported"] is None


def test_ping_reachability_skipped_when_base_offline(svc):
    with patch(
        f"{_MODULE}.get",
        side_effect=requests.exceptions.ConnectionError("refused"),
    ) as mock_get:
        results = svc.ping_components()
    named = {r["component"]: r for r in results}
    assert named["pump"]["reachability"] is None
    assert named["pump"]["reachability_supported"] is None
    # one call per component (base ping only, no is-reachable follow-up)
    assert mock_get.call_count == 2


def test_ping_component_sila2_success(mocker, svc):
    from tests.unit.test_clients_sila import FakeSilaClient

    mocker.patch("chemunited_workflow.clients.sila.SilaClient", FakeSilaClient)

    result = svc.ping_component("sila-pump")

    assert result["online"] is True
    assert result["url"] == "sila2://localhost:50999"
    assert result["status_code"] is None
    assert result["reachability"] is None
    assert result["reachability_supported"] is None


def test_ping_component_sila2_unreachable(svc):
    # relies on the file's autouse safety-net patch (SilaClient always raises)
    result = svc.ping_component("sila-pump")

    assert result["online"] is False
    assert result["error"] == "test-mock: no real sila2 server configured"


def test_ping_component_opcua_success(mocker, svc):
    from tests.unit.test_clients_opcua import FakeClient

    mocker.patch("chemunited_workflow.clients.opcua.Client", FakeClient)

    result = svc.ping_component("opc-valve")

    assert result["online"] is True
    assert result["url"] == "opc.tcp://localhost:4999/ns=2;s=Root"


def test_ping_component_unconfigured_sila2(svc):
    result = svc.ping_component("unconfigured-sila")
    assert result["online"] is False
    assert result["error"] == "not configured"


def test_ping_components_closes_all_clients(mocker, svc):
    close_spy_http = mocker.patch("chemunited_workflow.clients.http.BaseClient.close")
    svc.ping_components()
    # pump + valve (empty/unconfigured-* are never registered by Platform)
    assert close_spy_http.call_count == 2


# ── write_protocol main_parameter injection ───────────────────────────────────


def test_write_protocol_injects_main_parameter_when_absent(svc, tmp_path):
    filename = svc.write_protocol("test", {})
    data = json.loads((tmp_path / "protocols_historic" / filename).read_text())
    assert "main_parameter" in data
    assert data["main_parameter"] == {"x": 1.0}


def test_write_protocol_preserves_explicit_main_parameter(svc, tmp_path):
    filename = svc.write_protocol("test", {"main_parameter": {"x": 42.0}})
    data = json.loads((tmp_path / "protocols_historic" / filename).read_text())
    assert data["main_parameter"] == {"x": 42.0}


# ── get_component_commands ────────────────────────────────────────────────────

_FAKE_SCHEMA = {
    "paths": {
        "/sim/pump/infuse": {
            "put": {
                "parameters": [
                    {
                        "name": "rate",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "string", "default": "1 ml/min"},
                    }
                ]
            }
        },
        "/sim/pump/is-reachable": {"get": {"parameters": []}},
        "/sim/pump/position": {
            "get": {"parameters": []},
            "put": {"parameters": []},
        },
        "/sim/valve/position": {"get": {"parameters": []}},
    }
}


@resp_lib.activate
def test_get_component_commands_returns_commands_for_component(svc):
    resp_lib.add(
        resp_lib.GET,
        "http://device-server:8000/openapi.json",
        json=_FAKE_SCHEMA,
        status=200,
    )
    commands = svc.get_component_commands("pump")

    assert commands["infuse_put"]["type"] == "put"
    assert commands["infuse_put"]["parameters"]["rate"]["default"] == "1 ml/min"
    assert commands["is-reachable_get"]["type"] == "get"
    assert commands["position_get"]["name"] == "position"
    assert commands["position_put"]["name"] == "position"


def test_get_component_commands_unknown_component_raises(svc):
    with pytest.raises(KeyError):
        svc.get_component_commands("ghost")


@resp_lib.activate
def test_get_component_commands_closes_client(svc, mocker):
    resp_lib.add(
        resp_lib.GET,
        "http://device-server:8000/openapi.json",
        json=_FAKE_SCHEMA,
        status=200,
    )
    close_spy = mocker.patch("chemunited_workflow.clients.http.BaseClient.close")
    svc.get_component_commands("pump")
    close_spy.assert_called_once()


@resp_lib.activate
def test_get_component_commands_survives_close_failure(svc, mocker):
    """A close() failure must not mask a successful result, but should be logged."""
    resp_lib.add(
        resp_lib.GET,
        "http://device-server:8000/openapi.json",
        json=_FAKE_SCHEMA,
        status=200,
    )
    mocker.patch(
        "chemunited_workflow.clients.http.BaseClient.close",
        side_effect=RuntimeError("connection already gone"),
    )
    warning_spy = mocker.patch(
        "chemunited_workflow.api.services.protocol.logger.warning"
    )

    commands = svc.get_component_commands("pump")

    assert commands["position_get"]["name"] == "position"
    warning_spy.assert_called_once()


# ── send_component_command ──────────────────────────────────────────────────


@resp_lib.activate
def test_send_component_command_get_success(svc):
    resp_lib.add(
        resp_lib.GET,
        "http://device-server:8000/sim/pump/is-reachable",
        json="online",
        status=200,
    )
    result = svc.send_component_command("pump", "is-reachable", "get")

    assert result["ok"] is True
    assert result["status_code"] == 200
    assert result["response"] == "online"
    assert result["url"] == "http://device-server:8000/sim/pump/is-reachable"
    assert result["error"] is None
    assert isinstance(result["latency_ms"], int)


@resp_lib.activate
def test_send_component_command_put_success(svc):
    resp_lib.add(
        resp_lib.PUT,
        "http://device-server:8000/sim/pump/infuse",
        json={"rate": "5 ml/min"},
        status=200,
    )
    resp_lib.add(
        resp_lib.GET,
        "http://device-server:8000/sim/pump/is-idle",
        body=b"true",
        status=200,
    )
    result = svc.send_component_command(
        "pump", "infuse", "put", params={"rate": "5 ml/min"}
    )

    assert result["ok"] is True
    assert result["response"] == {"rate": "5 ml/min"}


@resp_lib.activate
def test_send_component_command_non_json_response_falls_back_to_text(svc):
    resp_lib.add(
        resp_lib.GET,
        "http://device-server:8000/sim/pump/raw",
        body="OK",
        status=200,
        content_type="text/plain",
    )
    result = svc.send_component_command("pump", "raw", "get")
    assert result["response"] == "OK"


@resp_lib.activate
def test_send_component_command_error_status(svc):
    resp_lib.add(
        resp_lib.GET,
        "http://device-server:8000/sim/pump/infuse",
        json={},
        status=503,
    )
    result = svc.send_component_command("pump", "infuse", "get")
    assert result["ok"] is False
    assert result["status_code"] == 503
    assert result["error"] == "HTTP 503"


@resp_lib.activate
def test_send_component_command_connection_error(svc):
    resp_lib.add(
        resp_lib.GET,
        "http://device-server:8000/sim/pump/infuse",
        body=requests.exceptions.ConnectionError("refused"),
    )
    result = svc.send_component_command("pump", "infuse", "get")
    assert result["ok"] is False
    assert result["status_code"] is None
    assert result["error"].startswith("ConnectionError")


@resp_lib.activate
def test_send_component_command_closes_client(svc, mocker):
    resp_lib.add(
        resp_lib.GET,
        "http://device-server:8000/sim/pump/is-reachable",
        json="online",
        status=200,
    )
    close_spy = mocker.patch("chemunited_workflow.clients.http.BaseClient.close")
    svc.send_component_command("pump", "is-reachable", "get")
    close_spy.assert_called_once()


def test_send_component_command_sila2_success(mocker, svc):
    from tests.unit.test_clients_sila import FakeFeature, FakeProperty, FakeSilaClient

    mocker.patch("chemunited_workflow.clients.sila.SilaClient", FakeSilaClient)
    feature = FakeFeature(
        "Thermostat",
        properties={"Temperature": FakeProperty("Temperature", value=21.5)},
    )

    def build_and_inject(*args, **kwargs):
        client = FakeSilaClient(*args, **kwargs)
        client._features[feature._identifier] = feature
        return client

    mocker.patch(
        "chemunited_workflow.clients.sila.SilaClient", side_effect=build_and_inject
    )

    result = svc.send_component_command("sila-pump", "Thermostat.Temperature", "get")

    assert result["ok"] is True
    assert result["status_code"] is None
    assert result["response"] == 21.5
    assert result["url"] == "sila2://localhost:50999/Thermostat.Temperature"


def test_send_component_command_sila2_device_error(mocker, svc):
    from tests.unit.test_clients_sila import FakeCommand, FakeFeature

    command = FakeCommand("SetPoint", error=RuntimeError("device offline"))
    feature = FakeFeature("Thermostat", commands={"SetPoint": command})

    def build_and_inject(*args, **kwargs):
        from tests.unit.test_clients_sila import FakeSilaClient

        client = FakeSilaClient(*args, **kwargs)
        client._features[feature._identifier] = feature
        return client

    mocker.patch(
        "chemunited_workflow.clients.sila.SilaClient", side_effect=build_and_inject
    )

    result = svc.send_component_command(
        "sila-pump", "Thermostat.SetPoint", "put", json_body={"value": 30}
    )

    assert result["ok"] is False
    assert result["status_code"] is None
    assert "device offline" in result["error"]


def test_send_component_command_opcua_success(mocker, svc):
    from tests.unit.test_clients_opcua import FakeClient, FakeNode

    temp_node = FakeNode(value=21.5)
    root = FakeNode(children={"2:Temperature": temp_node})

    def build_and_inject(endpoint):
        client = FakeClient(endpoint)
        client._root = root
        return client

    mocker.patch(
        "chemunited_workflow.clients.opcua.Client", side_effect=build_and_inject
    )

    result = svc.send_component_command("opc-valve", "2:Temperature", "get")

    assert result["ok"] is True
    assert result["response"] == 21.5


def test_send_component_command_unknown_component_raises(svc):
    with pytest.raises(KeyError):
        svc.send_component_command("ghost", "infuse", "get")


def test_send_component_command_unconfigured_component_raises(svc):
    with pytest.raises(ValueError):
        svc.send_component_command("empty", "infuse", "get")
