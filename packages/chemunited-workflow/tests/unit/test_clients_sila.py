"""Unit tests for SilaComponentClient — mocked sila2 client, no live server."""

from __future__ import annotations

import threading

import pytest
from sila2.client.client_observable_command_instance import (
    ClientObservableCommandInstance,
)

from chemunited_workflow.clients.base import _pop_thread_resilient_errors
from chemunited_workflow.clients.sila import SilaComponentClient
from chemunited_workflow.exceptions import (
    ConcurrentClientAccessError,
    SilaDeviceError,
)


class FakeParameter:
    def __init__(self, identifier, data_type_cls):
        self._identifier = identifier
        self.data_type = data_type_cls()


# Marker classes named after sila2's actual data-type classes, since
# SilaComponentClient reads the type name via `type(param.data_type).__name__`.
Integer = type("Integer", (), {})
String = type("String", (), {})


class FakeCommand:
    def __init__(
        self, identifier, parameters=(), response=None, error=None, description=""
    ):
        self._identifier = identifier
        self.parameters = list(parameters)
        self._response = response
        self._error = error
        self._description = description
        self.calls: list[dict] = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return self._response


class FakeObservableCommandInstance(ClientObservableCommandInstance):
    """Bypasses the real __init__ (no gRPC subscription thread needed for tests)."""

    def __init__(self, response=None, done_after=1):
        self._response = response
        self._done_after = done_after
        self._checks = 0

    @property
    def done(self):
        self._checks += 1
        return self._checks >= self._done_after

    @property
    def execution_uuid(self):
        return "fake-execution-uuid"

    def get_responses(self):
        return self._response


class FakeNeverDoneCommandInstance(ClientObservableCommandInstance):
    def __init__(self):
        pass

    @property
    def done(self):
        return False

    @property
    def execution_uuid(self):
        return "never-done"

    def get_responses(self):
        raise AssertionError("get_responses should not be called before completion")


class FakeObservableCommand:
    def __init__(self, identifier, instance_factory, description=""):
        self._identifier = identifier
        self.parameters = []
        self._instance_factory = instance_factory
        self._description = description
        self.calls: list[dict] = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return self._instance_factory(**kwargs)


class FakeProperty:
    def __init__(self, identifier, value=None, error=None, description=""):
        self._identifier = identifier
        self._value = value
        self._error = error
        self._description = description
        self.calls = 0

    def get(self):
        self.calls += 1
        if self._error is not None:
            raise self._error
        return self._value


class FakeFeature:
    def __init__(
        self, identifier, properties=None, commands=None, observable_commands=None
    ):
        self._identifier = identifier
        self._client_properties = dict(properties or {})
        self._client_commands = {**(commands or {}), **(observable_commands or {})}
        self._unobservable_properties = dict(properties or {})
        self._unobservable_commands = dict(commands or {})
        self._observable_commands = dict(observable_commands or {})


class FakeSilaClient:
    """Stand-in for sila2.client.SilaClient — no network I/O."""

    last_instance: "FakeSilaClient | None" = None

    def __init__(self, host, port, *, insecure=True, root_certs=None):
        self.host = host
        self.port = port
        self.insecure = insecure
        self._features: dict[str, FakeFeature] = {}
        self.closed = False
        FakeSilaClient.last_instance = self

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def _reset_resilient_errors():
    _pop_thread_resilient_errors()
    yield
    _pop_thread_resilient_errors()


def _client_with_feature(mocker, feature: FakeFeature, **kwargs) -> SilaComponentClient:
    mocker.patch("chemunited_workflow.clients.sila.SilaClient", FakeSilaClient)
    client = SilaComponentClient(host="localhost", port=50051, **kwargs)
    sila_client = (
        client._ensure_connected()
    )  # force connection so we can inject the fake feature
    sila_client._features[feature._identifier] = feature
    return client


def test_dry_run_never_connects(mocker):
    connect = mocker.patch("chemunited_workflow.clients.sila.SilaClient")
    client = SilaComponentClient(host="localhost", port=50051, dry_run=True)

    assert client.get("Thermostat.Temperature") == {}
    assert client.put("Thermostat.SetPoint", value=5) == {}
    connect.assert_not_called()


def test_get_returns_property_value(mocker):
    feature = FakeFeature(
        "Thermostat",
        properties={"Temperature": FakeProperty("Temperature", value=21.5)},
    )
    client = _client_with_feature(mocker, feature)

    assert client.get("Thermostat.Temperature") == 21.5


def test_get_raw_response_returns_same_value(mocker):
    feature = FakeFeature(
        "Thermostat",
        properties={"Temperature": FakeProperty("Temperature", value=21.5)},
    )
    client = _client_with_feature(mocker, feature)

    assert client.get("Thermostat.Temperature", raw_response=True) == 21.5


def test_put_calls_command_with_merged_params(mocker):
    command = FakeCommand("SetPoint", response={"accepted": True})
    feature = FakeFeature("Thermostat", commands={"SetPoint": command})
    client = _client_with_feature(mocker, feature)

    result = client.put("Thermostat.SetPoint", value=30)

    assert command.calls == [{"value": 30}]
    assert result == {"accepted": True}


def test_error_resilient_wraps_and_swallows(mocker):
    command = FakeCommand("SetPoint", error=RuntimeError("device offline"))
    feature = FakeFeature("Thermostat", commands={"SetPoint": command})
    client = _client_with_feature(mocker, feature, error_resilient=True)

    result = client.put("Thermostat.SetPoint", value=30)

    assert result == {}
    errors = _pop_thread_resilient_errors()
    assert len(errors) == 1
    assert isinstance(errors[0], SilaDeviceError)


def test_error_not_resilient_raises_sila_device_error(mocker):
    command = FakeCommand("SetPoint", error=RuntimeError("device offline"))
    feature = FakeFeature("Thermostat", commands={"SetPoint": command})
    client = _client_with_feature(mocker, feature)

    with pytest.raises(SilaDeviceError):
        client.put("Thermostat.SetPoint", value=30)


def test_concurrent_access_raises(mocker):
    feature = FakeFeature(
        "Thermostat", properties={"Temperature": FakeProperty("Temperature", value=1)}
    )
    client = _client_with_feature(mocker, feature)
    errors: list[Exception] = []

    client._access_lock.acquire()
    try:

        def attempt():
            try:
                client.get("Thermostat.Temperature")
            except ConcurrentClientAccessError as exc:
                errors.append(exc)

        t = threading.Thread(target=attempt)
        t.start()
        t.join(timeout=2.0)
        assert not t.is_alive()
    finally:
        client._access_lock.release()

    assert len(errors) == 1


def test_write_json_log(mocker, tmp_path):
    log_path = tmp_path / "thermostat.jsonl"
    feature = FakeFeature(
        "Thermostat", properties={"Temperature": FakeProperty("Temperature", value=1)}
    )
    client = _client_with_feature(mocker, feature, pool_json_log=log_path)

    client.get("Thermostat.Temperature")

    assert log_path.exists()


def test_put_awaits_observable_command_and_returns_responses(mocker):
    instance = FakeObservableCommandInstance(
        response={"FinalFillLevelMicroliters": 100.0}, done_after=3
    )
    command = FakeObservableCommand(
        "AspirateVolume", instance_factory=lambda **kw: instance
    )
    feature = FakeFeature(
        "FluidDosingService", observable_commands={"AspirateVolume": command}
    )
    client = _client_with_feature(mocker, feature)

    result = client.put("FluidDosingService.AspirateVolume", VolumeMicroliters=500.0)

    assert command.calls == [{"VolumeMicroliters": 500.0}]
    assert result == {"FinalFillLevelMicroliters": 100.0}
    assert instance._checks >= 3


def test_put_observable_command_times_out(mocker):
    command = FakeObservableCommand(
        "AspirateVolume", instance_factory=lambda **kw: FakeNeverDoneCommandInstance()
    )
    feature = FakeFeature(
        "FluidDosingService", observable_commands={"AspirateVolume": command}
    )
    client = _client_with_feature(mocker, feature, timeout_commands="0.05 s")

    with pytest.raises(SilaDeviceError, match="did not finish"):
        client.put("FluidDosingService.AspirateVolume", VolumeMicroliters=500.0)


def test_close_disconnects_and_is_idempotent(mocker):
    feature = FakeFeature(
        "Thermostat", properties={"Temperature": FakeProperty("Temperature", value=1)}
    )
    client = _client_with_feature(mocker, feature)
    fake_client = client._client

    client.close()

    assert fake_client.closed is True
    assert client._client is None
    client.close()  # must not raise when already closed


def test_connection_failure_wrapped_as_sila_device_error(mocker):
    mocker.patch(
        "chemunited_workflow.clients.sila.SilaClient",
        side_effect=RuntimeError("refused"),
    )
    client = SilaComponentClient(host="localhost", port=50051)

    with pytest.raises(SilaDeviceError):
        client.get("Thermostat.Temperature")


def test_connection_failure_resilient_swallows_error(mocker):
    mocker.patch(
        "chemunited_workflow.clients.sila.SilaClient",
        side_effect=RuntimeError("refused"),
    )
    client = SilaComponentClient(host="localhost", port=50051, error_resilient=True)

    result = client.get("Thermostat.Temperature")

    assert result == {}
    errors = _pop_thread_resilient_errors()
    assert len(errors) == 1
    assert isinstance(errors[0], SilaDeviceError)


def test_discover_commands_connection_failure_wrapped(mocker):
    mocker.patch(
        "chemunited_workflow.clients.sila.SilaClient",
        side_effect=RuntimeError("refused"),
    )
    client = SilaComponentClient(host="localhost", port=50051)

    with pytest.raises(SilaDeviceError):
        client.discover_commands()


def test_ping_succeeds_when_connectable(mocker):
    mocker.patch("chemunited_workflow.clients.sila.SilaClient", FakeSilaClient)
    client = SilaComponentClient(host="localhost", port=50051)

    client.ping()  # must not raise

    assert client._client is not None


def test_ping_raises_on_connection_failure(mocker):
    mocker.patch(
        "chemunited_workflow.clients.sila.SilaClient",
        side_effect=RuntimeError("refused"),
    )
    client = SilaComponentClient(host="localhost", port=50051)

    with pytest.raises(SilaDeviceError):
        client.ping()


def test_ping_resilient_swallows_connection_failure(mocker):
    mocker.patch(
        "chemunited_workflow.clients.sila.SilaClient",
        side_effect=RuntimeError("refused"),
    )
    client = SilaComponentClient(host="localhost", port=50051, error_resilient=True)

    client.ping()  # must not raise

    errors = _pop_thread_resilient_errors()
    assert len(errors) == 1
    assert isinstance(errors[0], SilaDeviceError)


def test_discover_commands_shape(mocker):
    feature = FakeFeature(
        "Thermostat",
        properties={
            "Temperature": FakeProperty(
                "Temperature", value=21.5, description="Current temperature reading"
            )
        },
        commands={
            "SetPoint": FakeCommand(
                "SetPoint",
                parameters=[FakeParameter("value", Integer)],
                description="Set the target temperature",
            )
        },
    )
    client = _client_with_feature(mocker, feature)

    commands = client.discover_commands()

    assert commands["Thermostat.Temperature_get"] == {
        "name": "Thermostat.Temperature",
        "type": "get",
        "parameters": {},
        "summary": "Current temperature reading",
    }
    assert commands["Thermostat.SetPoint_put"] == {
        "name": "Thermostat.SetPoint",
        "type": "put",
        "parameters": {"value": {"in": "body", "required": True, "type": "integer"}},
        "summary": "Set the target temperature",
    }
