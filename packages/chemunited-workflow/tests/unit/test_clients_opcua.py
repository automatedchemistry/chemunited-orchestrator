"""Unit tests for OpcUaComponentClient — mocked asyncua.sync client, no live server."""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest
from asyncua import ua

from chemunited_workflow.clients.base import _pop_thread_resilient_errors
from chemunited_workflow.clients.opcua import OpcUaComponentClient
from chemunited_workflow.exceptions import (
    ConcurrentClientAccessError,
    OpcUaDeviceError,
    RunCancelledError,
)


class FakeNode:
    def __init__(
        self,
        nodeid="fake-nodeid",
        node_class=ua.NodeClass.Variable,
        browse_name=None,
        value=None,
        values=None,
        writable=False,
        variant_type=ua.VariantType.Double,
        children=None,
        parent=None,
        error=None,
        description="",
    ):
        self.nodeid = nodeid
        self._node_class = node_class
        self._browse_name = browse_name
        self._value = value
        self._values = list(values) if values is not None else None
        self._description = description
        self._writable = writable
        self._variant_type = variant_type
        self._children = children or {}
        self._parent = parent
        self._error = error
        self.set_calls: list[object] = []
        self.method_calls: list[tuple] = []
        self.read_calls = 0

    def read_node_class(self):
        return self._node_class

    def read_browse_name(self):
        return self._browse_name

    def read_description(self):
        return SimpleNamespace(Text=self._description)

    def get_children(self):
        return list(self._children.values())

    def get_child(self, path):
        if self._error is not None:
            raise self._error
        return self._children[path]

    def get_value(self):
        self.read_calls += 1
        if self._error is not None:
            raise self._error
        if self._values is not None:
            if len(self._values) > 1:
                return self._values.pop(0)
            return self._values[0]
        return self._value

    def set_value(self, value):
        if self._error is not None:
            raise self._error
        self.set_calls.append(value)

    def get_access_level(self):
        return (
            {ua.AccessLevel.CurrentWrite}
            if self._writable
            else {ua.AccessLevel.CurrentRead}
        )

    def read_data_type_as_variant_type(self):
        return self._variant_type

    def get_parent(self):
        return self._parent

    def call_method(self, methodid, *args):
        self.method_calls.append((methodid, args))
        if self._error is not None:
            raise self._error
        return "ok"


class FakeClient:
    last_instance: "FakeClient | None" = None

    def __init__(self, endpoint):
        self.endpoint = endpoint
        self.connected = False
        self.user = None
        self.password = None
        self._root = FakeNode(node_class=ua.NodeClass.Object)
        FakeClient.last_instance = self

    def set_user(self, username):
        self.user = username

    def set_password(self, password):
        self.password = password

    def connect(self):
        self.connected = True

    def disconnect(self):
        self.connected = False

    def get_node(self, node_id):
        assert self.connected
        return self._root


@pytest.fixture(autouse=True)
def _reset_resilient_errors():
    _pop_thread_resilient_errors()
    yield
    _pop_thread_resilient_errors()


def _client_with_root(mocker, root: FakeNode, **kwargs) -> OpcUaComponentClient:
    mocker.patch("chemunited_workflow.clients.opcua.Client", FakeClient)
    client = OpcUaComponentClient(
        endpoint="opc.tcp://localhost:4840", root_node_id="ns=2;s=Root", **kwargs
    )
    client._root_node()  # force connection
    client._root = root
    return client


def test_dry_run_never_connects(mocker):
    connect = mocker.patch("chemunited_workflow.clients.opcua.Client")
    client = OpcUaComponentClient(
        endpoint="opc.tcp://localhost:4840", root_node_id="ns=2;s=Root", dry_run=True
    )

    assert client.get("2:Temperature") == {}
    assert client.put("2:SetPoint", value=5) == {}
    connect.assert_not_called()


def test_get_reads_variable_value(mocker):
    temp_node = FakeNode(value=21.5)
    root = FakeNode(
        node_class=ua.NodeClass.Object, children={"2:Temperature": temp_node}
    )
    client = _client_with_root(mocker, root)

    assert client.get("2:Temperature") == 21.5


def test_put_writes_variable_value(mocker):
    setpoint_node = FakeNode(node_class=ua.NodeClass.Variable, writable=True)
    root = FakeNode(
        node_class=ua.NodeClass.Object, children={"2:SetPoint": setpoint_node}
    )
    client = _client_with_root(mocker, root)

    client.put("2:SetPoint", json=42)

    assert setpoint_node.set_calls == [42]


def test_put_calls_method_with_positional_args(mocker):
    method_node = FakeNode(nodeid="method-1", node_class=ua.NodeClass.Method)
    method_node._parent = root = FakeNode(
        node_class=ua.NodeClass.Object, children={"2:Home": method_node}
    )
    client = _client_with_root(mocker, root)

    result = client.put("2:Home", speed=3)

    assert result == "ok"
    assert root.method_calls == [("method-1", (3,))]


def test_error_resilient_wraps_and_swallows(mocker):
    temp_node = FakeNode(error=RuntimeError("bad status code"))
    root = FakeNode(
        node_class=ua.NodeClass.Object, children={"2:Temperature": temp_node}
    )
    client = _client_with_root(mocker, root, error_resilient=True)

    assert client.get("2:Temperature") == {}
    errors = _pop_thread_resilient_errors()
    assert len(errors) == 1
    assert isinstance(errors[0], OpcUaDeviceError)


def test_error_not_resilient_raises_opcua_device_error(mocker):
    temp_node = FakeNode(error=RuntimeError("bad status code"))
    root = FakeNode(
        node_class=ua.NodeClass.Object, children={"2:Temperature": temp_node}
    )
    client = _client_with_root(mocker, root)

    with pytest.raises(OpcUaDeviceError):
        client.get("2:Temperature")


def test_concurrent_access_raises(mocker):
    temp_node = FakeNode(value=1)
    root = FakeNode(
        node_class=ua.NodeClass.Object, children={"2:Temperature": temp_node}
    )
    client = _client_with_root(mocker, root)
    errors: list[Exception] = []

    client._access_lock.acquire()
    try:

        def attempt():
            try:
                client.get("2:Temperature")
            except ConcurrentClientAccessError as exc:
                errors.append(exc)

        t = threading.Thread(target=attempt)
        t.start()
        t.join(timeout=2.0)
        assert not t.is_alive()
    finally:
        client._access_lock.release()

    assert len(errors) == 1


def test_close_disconnects_and_is_idempotent(mocker):
    temp_node = FakeNode(value=1)
    root = FakeNode(
        node_class=ua.NodeClass.Object, children={"2:Temperature": temp_node}
    )
    client = _client_with_root(mocker, root)
    fake_client = client._client

    client.close()

    assert fake_client.connected is False
    assert client._client is None
    assert client._root is None
    client.close()  # must not raise when already closed


def test_connection_failure_wrapped_as_opcua_device_error(mocker):
    mocker.patch(
        "chemunited_workflow.clients.opcua.Client", side_effect=RuntimeError("refused")
    )
    client = OpcUaComponentClient(
        endpoint="opc.tcp://localhost:4840", root_node_id="ns=2;s=Root"
    )

    with pytest.raises(OpcUaDeviceError):
        client.get("2:Temperature")


def test_connection_failure_resilient_swallows_error(mocker):
    mocker.patch(
        "chemunited_workflow.clients.opcua.Client", side_effect=RuntimeError("refused")
    )
    client = OpcUaComponentClient(
        endpoint="opc.tcp://localhost:4840",
        root_node_id="ns=2;s=Root",
        error_resilient=True,
    )

    result = client.get("2:Temperature")

    assert result == {}
    errors = _pop_thread_resilient_errors()
    assert len(errors) == 1
    assert isinstance(errors[0], OpcUaDeviceError)


def test_discover_commands_connection_failure_wrapped(mocker):
    mocker.patch(
        "chemunited_workflow.clients.opcua.Client", side_effect=RuntimeError("refused")
    )
    client = OpcUaComponentClient(
        endpoint="opc.tcp://localhost:4840", root_node_id="ns=2;s=Root"
    )

    with pytest.raises(OpcUaDeviceError):
        client.discover_commands()


def test_ping_succeeds_when_connectable(mocker):
    mocker.patch("chemunited_workflow.clients.opcua.Client", FakeClient)
    client = OpcUaComponentClient(
        endpoint="opc.tcp://localhost:4840", root_node_id="ns=2;s=Root"
    )

    client.ping()  # must not raise

    assert client._client is not None


def test_ping_raises_on_connection_failure(mocker):
    mocker.patch(
        "chemunited_workflow.clients.opcua.Client", side_effect=RuntimeError("refused")
    )
    client = OpcUaComponentClient(
        endpoint="opc.tcp://localhost:4840", root_node_id="ns=2;s=Root"
    )

    with pytest.raises(OpcUaDeviceError):
        client.ping()


def test_ping_resilient_swallows_connection_failure(mocker):
    mocker.patch(
        "chemunited_workflow.clients.opcua.Client", side_effect=RuntimeError("refused")
    )
    client = OpcUaComponentClient(
        endpoint="opc.tcp://localhost:4840",
        root_node_id="ns=2;s=Root",
        error_resilient=True,
    )

    client.ping()  # must not raise

    errors = _pop_thread_resilient_errors()
    assert len(errors) == 1
    assert isinstance(errors[0], OpcUaDeviceError)


def test_discover_commands_shape(mocker):
    input_args_node = FakeNode(
        value=[SimpleNamespace(Name="speed", DataType=ua.NodeId(6, 0))]
    )
    method_node = FakeNode(
        node_class=ua.NodeClass.Method,
        browse_name=ua.QualifiedName("Home", 2),
        children={"0:InputArguments": input_args_node},
    )
    readonly_var = FakeNode(
        node_class=ua.NodeClass.Variable,
        browse_name=ua.QualifiedName("Status", 2),
        writable=False,
        description="Current device status",
    )
    writable_var = FakeNode(
        node_class=ua.NodeClass.Variable,
        browse_name=ua.QualifiedName("SetPoint", 2),
        writable=True,
        variant_type=ua.VariantType.Double,
    )
    root = FakeNode(
        node_class=ua.NodeClass.Object,
        children={
            "2:Home": method_node,
            "2:Status": readonly_var,
            "2:SetPoint": writable_var,
        },
    )
    client = _client_with_root(mocker, root)

    commands = client.discover_commands()

    assert commands["2:Status_get"] == {
        "name": "2:Status",
        "type": "get",
        "parameters": {},
        "summary": "Current device status",
    }
    assert "2:Status_put" not in commands
    assert commands["2:SetPoint_get"] == {
        "name": "2:SetPoint",
        "type": "get",
        "parameters": {},
        "summary": "",
    }
    assert commands["2:SetPoint_put"] == {
        "name": "2:SetPoint",
        "type": "put",
        "parameters": {"value": {"in": "body", "required": True, "type": "number"}},
        "summary": "",
    }
    assert commands["2:Home_put"] == {
        "name": "2:Home",
        "type": "put",
        "parameters": {"speed": {"in": "body", "required": True, "type": "integer"}},
        "summary": "",
    }


# ── automatic wait-for-idle (configurable idle_node_path) ────────────────────


def test_put_waits_for_idle_node_before_returning(mocker):
    setpoint_node = FakeNode(node_class=ua.NodeClass.Variable, writable=True)
    busy_node = FakeNode(values=[True, True, False])
    root = FakeNode(
        node_class=ua.NodeClass.Object,
        children={"2:SetPoint": setpoint_node, "6:Diagnostics/6:IsBusy": busy_node},
    )
    mocker.patch.object(OpcUaComponentClient, "_sleep_interruptibly")
    client = _client_with_root(
        mocker, root, idle_node_path="6:Diagnostics/6:IsBusy", idle_value=False
    )

    client.put("2:SetPoint", json=42)

    assert busy_node.read_calls == 3


def test_get_does_not_poll_idle_node(mocker):
    temp_node = FakeNode(value=21.5)
    busy_node = FakeNode(value=True)
    root = FakeNode(
        node_class=ua.NodeClass.Object,
        children={"2:Temperature": temp_node, "6:Diagnostics/6:IsBusy": busy_node},
    )
    client = _client_with_root(
        mocker, root, idle_node_path="6:Diagnostics/6:IsBusy", idle_value=False
    )

    assert client.get("2:Temperature") == 21.5
    assert busy_node.read_calls == 0


def test_idle_wait_disabled_by_default(mocker):
    setpoint_node = FakeNode(node_class=ua.NodeClass.Variable, writable=True)
    root = FakeNode(
        node_class=ua.NodeClass.Object, children={"2:SetPoint": setpoint_node}
    )
    client = _client_with_root(mocker, root)  # no idle_node_path configured

    client.put("2:SetPoint", json=42)  # must not try to resolve a nonexistent idle node

    assert setpoint_node.set_calls == [42]


def test_idle_poll_timeout_raises(mocker):
    setpoint_node = FakeNode(node_class=ua.NodeClass.Variable, writable=True)
    busy_node = FakeNode(value=True)
    root = FakeNode(
        node_class=ua.NodeClass.Object,
        children={"2:SetPoint": setpoint_node, "6:Diagnostics/6:IsBusy": busy_node},
    )
    mocker.patch.object(OpcUaComponentClient, "_sleep_interruptibly")
    client = _client_with_root(
        mocker,
        root,
        idle_node_path="6:Diagnostics/6:IsBusy",
        idle_value=False,
        timeout_commands="0.01 s",
    )

    with pytest.raises(TimeoutError, match="0.01"):
        client.put("2:SetPoint", json=42)


def test_idle_poll_timeout_pushed_when_error_resilient(mocker):
    setpoint_node = FakeNode(node_class=ua.NodeClass.Variable, writable=True)
    busy_node = FakeNode(value=True)
    root = FakeNode(
        node_class=ua.NodeClass.Object,
        children={"2:SetPoint": setpoint_node, "6:Diagnostics/6:IsBusy": busy_node},
    )
    mocker.patch.object(OpcUaComponentClient, "_sleep_interruptibly")
    client = _client_with_root(
        mocker,
        root,
        idle_node_path="6:Diagnostics/6:IsBusy",
        idle_value=False,
        timeout_commands="0.01 s",
        error_resilient=True,
    )

    client.put("2:SetPoint", json=42)  # does not raise

    errors = _pop_thread_resilient_errors()
    assert len(errors) == 1
    assert isinstance(errors[0], TimeoutError)


def test_idle_poll_stops_when_cancelled(mocker):
    setpoint_node = FakeNode(node_class=ua.NodeClass.Variable, writable=True)
    busy_node = FakeNode(value=True)
    root = FakeNode(
        node_class=ua.NodeClass.Object,
        children={"2:SetPoint": setpoint_node, "6:Diagnostics/6:IsBusy": busy_node},
    )
    cancel_event = threading.Event()
    client = _client_with_root(
        mocker,
        root,
        idle_node_path="6:Diagnostics/6:IsBusy",
        idle_value=False,
        timeout_commands="",
        cancellation_token=cancel_event,
    )

    timer = threading.Timer(0.05, cancel_event.set)
    started = time.monotonic()
    timer.start()
    try:
        with pytest.raises(RunCancelledError):
            client.put("2:SetPoint", json=42)
    finally:
        timer.cancel()

    assert time.monotonic() - started < 1.0


def test_dry_run_put_does_not_poll_idle(mocker):
    connect = mocker.patch("chemunited_workflow.clients.opcua.Client")
    client = OpcUaComponentClient(
        endpoint="opc.tcp://localhost:4840",
        root_node_id="ns=2;s=Root",
        dry_run=True,
        idle_node_path="6:Diagnostics/6:IsBusy",
        idle_value=False,
    )

    assert client.put("2:SetPoint", json=42) == {}
    connect.assert_not_called()
