"""Transport-agnostic device-client semantics shared by every protocol client."""

from __future__ import annotations

import abc
import json
import threading
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from loguru import logger

from ..cancellation import raise_if_cancelled, sleep_interruptibly, wait_while_paused
from ..command_events import (
    CommandEvent,
    CommandEventKind,
    CommandObserver,
    current_node,
    next_call_id,
)
from ..device_locks import hold_device
from ..durations import parse_timeout_commands
from ..exceptions import ConcurrentClientAccessError
from .envelope import CommandResponse

_thread_resilient_errors = threading.local()


def _push_thread_resilient_error(exc: Exception) -> None:
    if not hasattr(_thread_resilient_errors, "errors"):
        _thread_resilient_errors.errors = []
    _thread_resilient_errors.errors.append(exc)


def _pop_thread_resilient_errors() -> list[Exception]:
    errors = getattr(_thread_resilient_errors, "errors", [])
    _thread_resilient_errors.errors = []
    return errors


def _thread_resilient_error_count() -> int:
    return len(getattr(_thread_resilient_errors, "errors", []))


def _thread_resilient_errors_since(count: int) -> list[Exception]:
    """Errors pushed after *count* were already on the list — read, never popped."""
    return list(getattr(_thread_resilient_errors, "errors", [])[count:])


def _json_safe(value: Any) -> Any:
    """Convert JSON-like values into a shape safe for logs and requests."""
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if is_dataclass(value) and not isinstance(value, type):
        return _json_safe(asdict(value))
    if isinstance(value, Path):
        return str(value)
    try:
        json.dumps(value)
    except TypeError:
        return str(value)
    return value


class DeviceClientMixin(abc.ABC):
    """Device-semantic wrapper — locking, JSON logging, cooperative cancellation.

    Operates over the normalized :class:`CommandResponse` envelope so it can sit
    on top of any transport (HTTP, SiLA2, OPC UA, ...); each transport supplies
    ``_transport_get``/``_transport_put``/``_transport_post``.
    """

    def _init_device_semantics(
        self,
        *,
        component_ui: str = "undefined",
        dry_run: bool = False,
        pool_json_log: Path | None = None,
        timeout_commands: str = "10 s",
        error_resilient: bool = False,
        cancellation_token: threading.Event | None = None,
        pause_event: threading.Event | None = None,
        command_observer: CommandObserver | None = None,
        wait_for_completion: bool = True,
    ) -> None:
        self._dry_run = dry_run
        self._access_lock = threading.Lock()
        self.component_ui = component_ui
        self.pool_json_log = pool_json_log
        self.timeout_commands = timeout_commands.strip()
        self._feedback_timeout = parse_timeout_commands(timeout_commands)
        self._error_resilient = error_resilient
        self._cancellation_token = cancellation_token
        self._pause_event = pause_event
        self._command_observer = command_observer
        # False: a PUT/POST returns once the device accepts it, without
        # waiting for the device to finish (the dashboard's device panel).
        self._wait_for_completion = wait_for_completion

    base_url: str

    def _device_key(self) -> str:
        """Key of this device's process-wide lock (see ``device_locks``)."""
        return self.component_ui if self.component_ui != "undefined" else self.base_url

    def _report(
        self,
        kind: CommandEventKind,
        call_id: int,
        path: str,
        params: Any | None,
        body: Any | None,
        error: BaseException | None = None,
    ) -> None:
        """Tell the command observer (the live view) how a command is going.

        Never raises: a broken observer must not fail the command itself.
        """
        if self._command_observer is None:
            return
        try:
            self._command_observer(
                CommandEvent(
                    kind=kind,
                    component=self.component_ui,
                    command=path,
                    call_id=call_id,
                    params=dict(params) if isinstance(params, Mapping) else None,
                    body=body,
                    node=current_node(),
                    error=(
                        None if error is None else (str(error) or type(error).__name__)
                    ),
                )
            )
        except Exception:
            logger.opt(exception=True).warning(
                "Command observer failed for {} {}", self.component_ui, path
            )

    def _write_json_log(self, data: dict[str, Any]) -> None:
        if self.pool_json_log is None:
            return
        self.pool_json_log.parent.mkdir(parents=True, exist_ok=True)
        with self.pool_json_log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(_json_safe(data)) + "\n")

    def _raise_if_cancelled(self) -> None:
        raise_if_cancelled(self._cancellation_token)

    def _wait_if_paused(self) -> None:
        wait_while_paused(self._pause_event, self._cancellation_token)

    def _checkpoint(self) -> None:
        """Hold while paused, then raise if the run was cancelled."""
        self._wait_if_paused()
        self._raise_if_cancelled()

    def _sleep_interruptibly(self, duration: float) -> None:
        sleep_interruptibly(duration, self._cancellation_token, self._pause_event)

    @staticmethod
    def _merge_query_params(
        params: Any | None,
        command_params: dict[str, Any],
    ) -> Any | None:
        if params is None:
            return command_params or None
        if not command_params:
            return params
        if not isinstance(params, Mapping):
            raise TypeError(
                "ComponentClient command keyword params can only be combined with "
                "mapping-style params."
            )
        return {**params, **command_params}

    def _execute_post_command(self, verb: str) -> None:
        """Hook for protocol-specific post-command behavior. No-op by default."""

    # ── transport hooks — one implementation per protocol ────────────────────

    @abc.abstractmethod
    def _transport_get(self, path: str, *, params: Any | None) -> CommandResponse: ...

    @abc.abstractmethod
    def _transport_put(
        self, path: str, *, params: Any | None, json: Any | None
    ) -> CommandResponse: ...

    @abc.abstractmethod
    def _transport_post(
        self, path: str, *, params: Any | None, json: Any | None
    ) -> CommandResponse: ...

    # ── shared verb orchestration ─────────────────────────────────────────────

    def _call(
        self,
        verb: str,
        path: str,
        *,
        raw_response: bool,
        params: Any | None,
        json_body: Any | None,
        command_params: dict[str, Any],
    ) -> Any:
        query_params = self._merge_query_params(params, command_params)
        safe_query_params = _json_safe(query_params)
        safe_json = _json_safe(json_body) if json_body is not None else None
        self._write_json_log(
            {
                "component": self.component_ui,
                "method": verb.upper(),
                "command": path,
                "params": safe_query_params,
            }
        )
        self._checkpoint()
        if not self._access_lock.acquire(blocking=False):
            raise ConcurrentClientAccessError(
                f"{type(self).__name__}(url={self.base_url!r}) was accessed from two threads "
                "simultaneously. Each ComponentClient must be used by only one workflow node "
                "at a time — check your workflow graph for nodes that share the same device."
            )
        is_command = verb in ("put", "post")
        call_id = next_call_id() if is_command else 0
        # Resilient errors are pushed rather than raised; counting them before
        # and after (without popping) is how a pushed failure is noticed here.
        errors_before = _thread_resilient_error_count()
        try:
            if is_command:
                self._report("started", call_id, path, safe_query_params, safe_json)
            with hold_device(self._device_key()):
                if verb == "get":
                    resp = self._transport_get(path, params=safe_query_params)
                elif verb == "put":
                    resp = self._transport_put(
                        path, params=safe_query_params, json=safe_json
                    )
                else:
                    resp = self._transport_post(
                        path, params=safe_query_params, json=safe_json
                    )
            self._checkpoint()
        except BaseException as exc:
            if is_command:
                self._report("failed", call_id, path, safe_query_params, safe_json, exc)
            raise
        finally:
            self._access_lock.release()
        if not is_command:
            self._execute_post_command(verb)
            return resp.native if raw_response else resp.body_fn()
        try:
            self._execute_post_command(verb)
        except BaseException as exc:
            self._report("failed", call_id, path, safe_query_params, safe_json, exc)
            raise
        pushed = _thread_resilient_errors_since(errors_before)
        if pushed:
            self._report(
                "failed", call_id, path, safe_query_params, safe_json, pushed[-1]
            )
        else:
            self._report("finished", call_id, path, safe_query_params, safe_json)
        return resp.native if raw_response else resp.body_fn()

    def get(
        self,
        path: str,
        *,
        raw_response: bool = False,
        params: Any | None = None,
        **command_params: Any,
    ) -> Any:
        return self._call(
            "get",
            path,
            raw_response=raw_response,
            params=params,
            json_body=None,
            command_params=command_params,
        )

    def put(
        self,
        path: str,
        *,
        raw_response: bool = False,
        params: Any | None = None,
        json: Any | None = None,
        **command_params: Any,
    ) -> Any:
        return self._call(
            "put",
            path,
            raw_response=raw_response,
            params=params,
            json_body=json,
            command_params=command_params,
        )

    def post(
        self,
        path: str,
        *,
        raw_response: bool = False,
        params: Any | None = None,
        json: Any | None = None,
        **command_params: Any,
    ) -> Any:
        return self._call(
            "post",
            path,
            raw_response=raw_response,
            params=params,
            json_body=json,
            command_params=command_params,
        )
