"""OPC UA device client.

Requires the ``asyncua`` package (``pip install chemunited-workflow[opcua]``).
Built on ``asyncua.sync.Client`` — the actively-maintained ``asyncua``
library's synchronous facade, which runs its own background event-loop
thread internally, so no custom async-bridging shim is needed here. The
connection is made lazily on first use (not in ``__init__``) so that simply
constructing/loading a ``Platform`` never requires every configured OPC UA
server to be reachable.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from asyncua import ua
from asyncua.sync import Client, SyncNode
from loguru import logger

from ..exceptions import OpcUaDeviceError
from .base import DeviceClientMixin, _push_thread_resilient_error
from .envelope import CommandResponse

_VARIANT_TYPE_NAMES = {
    "Boolean": "boolean",
    "SByte": "integer",
    "Byte": "integer",
    "Int16": "integer",
    "UInt16": "integer",
    "Int32": "integer",
    "UInt32": "integer",
    "Int64": "integer",
    "UInt64": "integer",
    "Float": "number",
    "Double": "number",
    "String": "string",
}

# OPC UA Part 6 built-in DataType NodeIds (namespace 0) — stable per the spec.
_OPCUA_BUILTIN_DATATYPE_IDS = {
    1: "boolean",
    2: "integer",
    3: "integer",
    4: "integer",
    5: "integer",
    6: "integer",
    7: "integer",
    8: "integer",
    9: "integer",
    10: "number",
    11: "number",
    12: "string",
}


class OpcUaComponentClient(DeviceClientMixin):
    """Device-semantic OPC UA client — Variable reads map to ``get``, Variable
    writes and Method calls map to ``put`` (``post`` aliased to ``put``: OPC
    UA has no third verb, kept only so a dispatcher that only ever looks up
    ``get``/``put`` still finds a callable). ``path`` is a browse-name path
    relative to the configured root node, e.g. ``"2:Temperature"``.

    If ``idle_node_path`` is set, every ``put``/``post`` blocks afterwards
    until that node's value equals ``idle_value`` — the OPC UA/LADS analog
    of flowchem's ``GET /is-idle`` wait, since there's no single node path
    shared by every OPC UA device the way flowchem fixes ``is-idle``.
    """

    def __init__(
        self,
        *,
        endpoint: str,
        root_node_id: str,
        username: str | None = None,
        password: str | None = None,
        idle_node_path: str | None = None,
        idle_value: Any = False,
        component_ui: str = "undefined",
        dry_run: bool = False,
        pool_json_log: Path | None = None,
        timeout_commands: str = "10 s",
        error_resilient: bool = False,
        cancellation_token: threading.Event | None = None,
        pause_event: threading.Event | None = None,
    ) -> None:
        self._endpoint = endpoint
        self._root_node_id = root_node_id
        self._username = username
        self._password = password
        self._idle_node_path = idle_node_path
        self._idle_value = idle_value
        self._client: Client | None = None
        self._root: SyncNode | None = None
        self.base_url = f"{endpoint}/{root_node_id}"
        self._init_device_semantics(
            component_ui=component_ui,
            dry_run=dry_run,
            pool_json_log=pool_json_log,
            timeout_commands=timeout_commands,
            error_resilient=error_resilient,
            cancellation_token=cancellation_token,
            pause_event=pause_event,
        )

    def _ensure_connected(self) -> Client:
        if self._client is None:
            client = Client(self._endpoint)
            if self._username is not None:
                client.set_user(self._username)
            if self._password is not None:
                client.set_password(self._password)
            client.connect()
            self._client = client
        return self._client

    def close(self) -> None:
        """Disconnect and stop the background event-loop thread, if connected.

        asyncua.sync.Client runs its own event-loop thread for the life of the
        connection; without an explicit disconnect, a process that only ever
        constructs this client never exits.
        """
        if self._client is not None:
            self._client.disconnect()
            self._client = None
            self._root = None

    def ping(self) -> None:
        """Cheap reachability probe: one Read call confirming the configured root node
        resolves — cheaper than discover_commands()'s full Browse + per-child reads.
        Honors error_resilient the same way get/put do (see _handle_native_error)."""
        try:
            self._root_node().read_node_class()
        except Exception as exc:
            self._handle_native_error(exc)

    def _root_node(self) -> SyncNode:
        if self._root is None:
            self._root = self._ensure_connected().get_node(self._root_node_id)
        return self._root

    def _resolve(self, path: str) -> SyncNode:
        return self._root_node().get_child(path)

    def _handle_native_error(self, exc: Exception) -> CommandResponse:
        wrapped = OpcUaDeviceError(str(exc))
        if self._error_resilient:
            logger.error("OPC UA client error (error_resilient=True): {}", wrapped)
            _push_thread_resilient_error(wrapped)
            return CommandResponse(native=None, text="{}", body_fn=lambda: {})
        raise wrapped from exc

    def _transport_get(self, path: str, *, params: Any | None) -> CommandResponse:
        if self._dry_run:
            return CommandResponse(native=None, text="{}", body_fn=lambda: {})
        try:
            value = self._resolve(path).get_value()
        except Exception as exc:
            return self._handle_native_error(exc)
        return CommandResponse(native=value, text=str(value), body_fn=lambda: value)

    def _transport_put(
        self, path: str, *, params: Any | None, json: Any | None
    ) -> CommandResponse:
        if self._dry_run:
            return CommandResponse(native=None, text="{}", body_fn=lambda: {})
        try:
            node = self._resolve(path)
            if node.read_node_class() == ua.NodeClass.Method:
                args: list[Any] = (
                    list(params.values()) if isinstance(params, Mapping) else []
                )
                if isinstance(json, Mapping):
                    args.extend(json.values())
                elif json is not None:
                    args.append(json)
                result = node.get_parent().call_method(node.nodeid, *args)
            else:
                node.set_value(json if json is not None else params)
                result = None
        except Exception as exc:
            return self._handle_native_error(exc)
        return CommandResponse(native=result, text=str(result), body_fn=lambda: result)

    _transport_post = _transport_put

    # ── automatic wait-for-idle ─────────────────────────────────────────────
    # Unlike flowchem's fixed GET /is-idle, OPC UA/LADS has no single node
    # path shared by every device, so this is opt-in: only polls when
    # ``idle_node_path`` is configured (e.g. from an association's
    # "opcua_idle_path"/"opcua_idle_value"). A put/post is a command that can
    # make the device busy, so we block until the configured node reports the
    # configured idle value — a get is a passive read and never triggers this.

    def _execute_post_command(self, verb: str) -> None:
        if (
            verb in ("put", "post")
            and not self._dry_run
            and self._idle_node_path is not None
        ):
            self._wait_until_idle()

    def _wait_until_idle(self) -> None:
        if self._idle_node_path is None:
            raise OpcUaDeviceError(
                "_wait_until_idle called without an idle_node_path configured"
            )
        deadline = (
            None
            if self._feedback_timeout is None
            else time.monotonic() + self._feedback_timeout
        )
        while True:
            self._raise_if_cancelled()
            try:
                value = self._resolve(self._idle_node_path).get_value()
            except Exception as exc:
                wrapped = OpcUaDeviceError(str(exc))
                if self._error_resilient:
                    logger.error(
                        "OPC UA client error (error_resilient=True): {}", wrapped
                    )
                    _push_thread_resilient_error(wrapped)
                    return
                raise wrapped from exc

            if isinstance(value, ua.LocalizedText):
                value = value.Text

            if value == self._idle_value:
                return

            if deadline is not None and time.monotonic() >= deadline:
                timeout_exc = TimeoutError(
                    f"OPC UA node {self._idle_node_path!r} did not reach idle value "
                    f"{self._idle_value!r} within {self._feedback_timeout}s"
                )
                if self._error_resilient:
                    logger.error(
                        "Client timeout (error_resilient=True): {}", timeout_exc
                    )
                    _push_thread_resilient_error(timeout_exc)
                    return
                raise timeout_exc

            self._sleep_interruptibly(1.0)

    def discover_commands(self, timeout: float = 5.0) -> dict[str, dict[str, Any]]:
        """Enumerate direct children of the root node only (v1 scope, no
        recursion). Variables -> ``{name}_get`` always, also ``{name}_put``
        when writable; Methods -> ``{name}_put`` with parameters read from
        the method's ``InputArguments`` property. ``summary`` is each node's
        standard OPC UA ``Description`` attribute.
        """
        try:
            root = self._root_node()
        except Exception as exc:
            raise OpcUaDeviceError(str(exc)) from exc
        commands: dict[str, dict[str, Any]] = {}
        for child in root.get_children():
            node_class = child.read_node_class()
            browse_name = child.read_browse_name()
            name = f"{browse_name.NamespaceIndex}:{browse_name.Name}"
            summary = self._read_summary(child)
            if node_class == ua.NodeClass.Variable:
                commands[f"{name}_get"] = {
                    "name": name,
                    "type": "get",
                    "parameters": {},
                    "summary": summary,
                }
                if ua.AccessLevel.CurrentWrite in child.get_access_level():
                    variant_type = child.read_data_type_as_variant_type()
                    commands[f"{name}_put"] = {
                        "name": name,
                        "type": "put",
                        "parameters": {
                            "value": {
                                "in": "body",
                                "required": True,
                                "type": _VARIANT_TYPE_NAMES.get(
                                    variant_type.name, "object"
                                ),
                            }
                        },
                        "summary": summary,
                    }
            elif node_class == ua.NodeClass.Method:
                commands[f"{name}_put"] = {
                    "name": name,
                    "type": "put",
                    "parameters": self._extract_method_parameters(child),
                    "summary": summary,
                }
        return commands

    @staticmethod
    def _read_summary(node: SyncNode) -> str:
        try:
            description = node.read_description()
        except Exception:
            return ""
        if description is None:
            return ""
        return description.Text or ""

    @staticmethod
    def _extract_method_parameters(method_node: SyncNode) -> dict[str, dict[str, Any]]:
        parameters: dict[str, dict[str, Any]] = {}
        try:
            arguments = method_node.get_child("0:InputArguments").get_value() or []
        except Exception:
            return parameters
        for arg in arguments:
            arg_type = "object"
            if arg.DataType.NamespaceIndex == 0:
                arg_type = _OPCUA_BUILTIN_DATATYPE_IDS.get(
                    arg.DataType.Identifier, "object"
                )
            parameters[arg.Name] = {"in": "body", "required": True, "type": arg_type}
        return parameters
