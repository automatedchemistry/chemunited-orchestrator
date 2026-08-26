"""SiLA2 device client.

Requires the ``sila2`` package (``pip install chemunited-workflow[sila2]``).
Built on ``sila2.client.SilaClient``, which uses plain blocking gRPC stubs —
no async bridging needed. The connection is made lazily on first use (not in
``__init__``) so that simply constructing/loading a ``Platform`` never
requires every configured SiLA2 server to be reachable.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from loguru import logger
from sila2.client import SilaClient
from sila2.client.client_observable_command_instance import (
    ClientObservableCommandInstance,
)

from ..exceptions import SilaDeviceError
from .base import DeviceClientMixin, _push_thread_resilient_error
from .envelope import CommandResponse

_BASIC_TYPE_NAMES = {
    "Integer": "integer",
    "Real": "number",
    "String": "string",
    "Boolean": "boolean",
}


class SilaComponentClient(DeviceClientMixin):
    """Device-semantic SiLA2 client — SiLA Property reads map to ``get``, SiLA
    Command execution maps to ``put`` (``post`` aliased to ``put``: SiLA2 has
    no third verb, kept only so a dispatcher that only ever looks up
    ``get``/``put`` still finds a callable).
    """

    def __init__(
        self,
        *,
        host: str,
        port: int,
        insecure: bool = True,
        root_certs: bytes | None = None,
        component_ui: str = "undefined",
        dry_run: bool = False,
        pool_json_log: Path | None = None,
        timeout_commands: str = "10 s",
        error_resilient: bool = False,
        cancellation_token: threading.Event | None = None,
        pause_event: threading.Event | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._insecure = insecure
        self._root_certs = root_certs
        self._client: SilaClient | None = None
        self.base_url = f"sila2://{host}:{port}"
        self._init_device_semantics(
            component_ui=component_ui,
            dry_run=dry_run,
            pool_json_log=pool_json_log,
            timeout_commands=timeout_commands,
            error_resilient=error_resilient,
            cancellation_token=cancellation_token,
            pause_event=pause_event,
        )

    def _ensure_connected(self) -> SilaClient:
        if self._client is None:
            self._client = SilaClient(
                self._host,
                self._port,
                insecure=self._insecure,
                root_certs=self._root_certs,
            )
        return self._client

    def close(self) -> None:
        """Close the gRPC channel, if connected."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def ping(self) -> None:
        """Cheap reachability probe: SilaClient's constructor already performs SiLA2's
        mandatory SiLAService handshake, so a bare connect is the full check. Honors
        error_resilient the same way get/put do (see _handle_native_error)."""
        try:
            self._ensure_connected()
        except Exception as exc:
            self._handle_native_error(exc)

    @staticmethod
    def _resolve(path: str) -> tuple[str, str]:
        feature_id, _, member_id = path.partition(".")
        if not member_id:
            raise ValueError(
                f"SiLA2 command path must be 'Feature.Member', got {path!r}"
            )
        return feature_id, member_id

    def _handle_native_error(self, exc: Exception) -> CommandResponse:
        wrapped = SilaDeviceError(str(exc))
        if self._error_resilient:
            logger.error("SiLA2 client error (error_resilient=True): {}", wrapped)
            _push_thread_resilient_error(wrapped)
            return CommandResponse(native=None, text="{}", body_fn=lambda: {})
        raise wrapped from exc

    def _transport_get(self, path: str, *, params: Any | None) -> CommandResponse:
        if self._dry_run:
            return CommandResponse(native=None, text="{}", body_fn=lambda: {})
        feature_id, member_id = self._resolve(path)
        try:
            client = self._ensure_connected()
            prop = client._features[feature_id]._client_properties[member_id]
            value = prop.get()
        except Exception as exc:
            return self._handle_native_error(exc)
        return CommandResponse(native=value, text=str(value), body_fn=lambda: value)

    def _transport_put(
        self, path: str, *, params: Any | None, json: Any | None
    ) -> CommandResponse:
        if self._dry_run:
            return CommandResponse(native=None, text="{}", body_fn=lambda: {})
        feature_id, member_id = self._resolve(path)
        kwargs: dict[str, Any] = dict(params) if isinstance(params, Mapping) else {}
        if isinstance(json, Mapping):
            kwargs.update(json)
        elif json is not None:
            kwargs["body"] = json
        try:
            client = self._ensure_connected()
            command = client._features[feature_id]._client_commands[member_id]
            result = command(**kwargs)
            if isinstance(result, ClientObservableCommandInstance):
                result = self._await_observable_command(result)
        except Exception as exc:
            return self._handle_native_error(exc)
        value = result._asdict() if hasattr(result, "_asdict") else result
        return CommandResponse(native=result, text=str(value), body_fn=lambda: value)

    _transport_post = _transport_put

    def _await_observable_command(
        self, instance: ClientObservableCommandInstance
    ) -> Any:
        """Block until an observable command finishes, then return its responses.

        Status/progress are pushed by a background subscription thread that
        sila2 starts when the command is invoked, so this only needs to poll
        the local ``.done`` flag — no extra RPCs are made here.
        """
        deadline = (
            None
            if self._feedback_timeout is None
            else time.monotonic() + self._feedback_timeout
        )
        while not instance.done:
            self._raise_if_cancelled()
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError(
                    f"SiLA2 observable command {instance.execution_uuid} did not finish "
                    f"within {self._feedback_timeout}s"
                )
            self._sleep_interruptibly(0.2)
        return instance.get_responses()

    def discover_commands(self, timeout: float = 5.0) -> dict[str, dict[str, Any]]:
        """Enumerate SiLA2 properties/commands (observable and unobservable;
        observable *properties* are still skipped — this client does not yet
        subscribe to value updates). Properties -> ``{Feature}.{Member}_get``;
        commands -> ``{Feature}.{Member}_put``. Calling a ``put`` for an
        observable command blocks until the SiLA server reports completion.
        ``summary`` is each Command/Property's Feature Definition
        ``Description`` (mandatory in the FDL, unlike OpenAPI's optional
        ``summary``).
        """
        try:
            client = self._ensure_connected()
        except Exception as exc:
            raise SilaDeviceError(str(exc)) from exc
        commands: dict[str, dict[str, Any]] = {}
        for feature_id, feature in client._features.items():
            for identifier, prop in feature._unobservable_properties.items():
                name = f"{feature_id}.{identifier}"
                commands[f"{name}_get"] = {
                    "name": name,
                    "type": "get",
                    "parameters": {},
                    "summary": prop._description,
                }
            all_commands = {
                **feature._unobservable_commands,
                **feature._observable_commands,
            }
            for identifier, cmd in all_commands.items():
                name = f"{feature_id}.{identifier}"
                commands[f"{name}_put"] = {
                    "name": name,
                    "type": "put",
                    "parameters": self._extract_parameters(cmd),
                    "summary": cmd._description,
                }
        return commands

    @staticmethod
    def _extract_parameters(cmd: Any) -> dict[str, dict[str, Any]]:
        parameters: dict[str, dict[str, Any]] = {}
        for param in cmd.parameters:
            parameters[param._identifier] = {
                "in": "body",
                "required": True,
                "type": _BASIC_TYPE_NAMES.get(type(param.data_type).__name__, "object"),
            }
        return parameters
