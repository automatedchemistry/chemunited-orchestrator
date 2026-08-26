"""HTTP (flowchem/FastAPI) device client."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests
from loguru import logger
from pydantic import AnyHttpUrl

from .base import DeviceClientMixin, _push_thread_resilient_error
from .envelope import CommandResponse

_IS_IDLE_PATH = "is-idle"
_MIN_FLOWCHEM_VERSION = "1.1.3"


class BaseClient:
    """HTTP session wrapper — owns mechanics: URL building, verb methods, hooks, _request."""

    def __init__(self, url: str | AnyHttpUrl, *, dry_run: bool = False) -> None:
        self.base_url = str(url).rstrip("/")
        self._dry_run = dry_run
        self._last_log_msg: str | None = None
        self._log_count: int = 0
        self._session = self._make_session()

    def _make_session(self) -> requests.Session:
        session = requests.Session()
        session.hooks["response"] = [
            self._log_response,
            self._raise_for_status,
        ]
        return session

    def _build_url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    def _make_dry_response(self) -> requests.Response:
        """Return a synthetic 200 OK with an empty JSON body used in dry-run mode.

        Node methods that inspect the response body will receive no data — dry-run
        validates workflow feasibility (graph traversal, routing) not device behaviour.
        The body is `{}` rather than truly empty so that `.json()` (the default return
        value of ComponentClient's get/put/post) succeeds during dry runs.
        """
        response = requests.Response()
        response.status_code = 200
        response._content = b"{}"
        response.headers["Content-Type"] = "application/json"
        return response

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        if self._dry_run:
            req_body = kwargs.get("json") or kwargs.get("data")
            req_content_type = "application/json" if "json" in kwargs else "<none>"
            self._log(
                label="DRY RUN",
                method=method,
                url=self._build_url(path),
                req_body=str(req_body) if req_body else None,
                req_content_type=req_content_type,
                status_code=200,
                resp_content_type="application/json",
                resp_size=0,
                elapsed_ms=0.0,
                resp_preview="<empty>",
            )
            return self._make_dry_response()
        return self._session.request(method, self._build_url(path), **kwargs)

    def _log_response(self, response: requests.Response, *args, **kwargs) -> None:
        req_body = response.request.body
        if isinstance(req_body, bytes):
            try:
                req_body = req_body.decode()
            except UnicodeDecodeError:
                req_body = f"<binary {len(req_body)} bytes>"

        resp_content = response.content
        resp_size = len(resp_content)
        try:
            resp_preview = resp_content.decode("utf-8", errors="replace")[:200]
            if resp_size > 200:
                resp_preview += "…"
        except Exception:
            resp_preview = f"<binary {resp_size} bytes>"

        self._log(
            label="REQUEST",
            method=response.request.method or "",
            url=response.request.url or "",
            req_body=req_body,
            req_content_type=response.request.headers.get("Content-Type"),
            status_code=response.status_code,
            resp_content_type=response.headers.get("Content-Type"),
            resp_size=resp_size,
            elapsed_ms=response.elapsed.total_seconds() * 1000,
            resp_preview=resp_preview,
        )

    def _log(
        self,
        *,
        label: str,
        method: str,
        url: str,
        req_body: str | None,
        req_content_type: str | None,
        status_code: int,
        resp_content_type: str | None,
        resp_size: int,
        elapsed_ms: float,
        resp_preview: str | None,
    ) -> None:
        msg = (
            f"{label}: {method} {url}"
            f" | Request: {req_body or '<no body>'} {req_content_type or '<none>'}"
            f" | Response: {status_code} ({resp_content_type or '<none>'})"
            f" {resp_size}B in {elapsed_ms:.0f}ms"
            f" | Body: {resp_preview or '<empty>'}"
        )

        if msg == self._last_log_msg:
            self._log_count += 1
            return

        if self._log_count > 1:
            logger.debug("(last message repeated {} times)", self._log_count)

        logger.debug(msg)
        self._last_log_msg = msg
        self._log_count = 1

    def _raise_for_status(self, response: requests.Response, *args, **kwargs) -> None:
        response.raise_for_status()

    def close(self) -> None:
        """Release pooled HTTP connections.

        Not strictly required (no background thread/gRPC channel like the
        sila2/opcua clients), but lets call sites that build a throwaway
        client call ``.close()`` unconditionally regardless of protocol.
        """
        self._session.close()

    def get(self, path: str, *, params=None, **kwargs) -> requests.Response:
        return self._request("GET", path, params=params, **kwargs)

    def put(self, path: str, *, params=None, json=None, **kwargs) -> requests.Response:
        return self._request("PUT", path, params=params, json=json, **kwargs)

    def post(self, path: str, *, params=None, json=None, **kwargs) -> requests.Response:
        return self._request("POST", path, params=params, json=json, **kwargs)

    def discover_commands(self, timeout: float = 5.0) -> dict[str, dict[str, Any]]:
        """Return this component's exposed commands, keyed by ``{command}_{verb}``.

        FastAPI/flowchem-specific: fetches the device server's live
        ``openapi.json`` (served at the server root, not per-component) and
        filters it down to paths under this client's own ``base_url``. A
        different client implementation (e.g. SILA, OPC-UA) would override
        this method with its own protocol-appropriate discovery mechanism.

        A command path can expose both ``get`` and ``put`` (e.g. ``position``),
        so entries are keyed by ``{command}_{verb}`` rather than by the bare
        command name to avoid one verb overwriting the other; the raw command
        name is preserved in each entry's ``"name"`` field.
        """
        parts = urlsplit(self.base_url)
        root = f"{parts.scheme}://{parts.netloc}"
        prefix = parts.path.rstrip("/") + "/"

        response = self._session.request("GET", f"{root}/openapi.json", timeout=timeout)
        response.raise_for_status()
        schema = response.json()

        commands: dict[str, dict[str, Any]] = {}
        for path, methods in schema.get("paths", {}).items():
            if not path.startswith(prefix) or not isinstance(methods, dict):
                continue
            command = path[len(prefix) :]
            for verb in ("get", "put"):
                op = methods.get(verb)
                if op is None:
                    continue
                commands[f"{command}_{verb}"] = {
                    "name": command,
                    "type": verb,
                    "parameters": self._extract_parameters(op),
                }
        return commands

    @staticmethod
    def _extract_parameters(op: dict[str, Any]) -> dict[str, dict[str, Any]]:
        parameters: dict[str, dict[str, Any]] = {}
        for param in op.get("parameters", []):
            param_schema = param.get("schema", {})
            entry: dict[str, Any] = {
                "in": param.get("in", "query"),
                "required": param.get("required", False),
                "type": param_schema.get("type"),
            }
            if "default" in param_schema:
                entry["default"] = param_schema["default"]
            parameters[param["name"]] = entry

        request_body = op.get("requestBody")
        if request_body:
            body_schema = (
                request_body.get("content", {})
                .get("application/json", {})
                .get("schema", {})
            )
            parameters["body"] = {
                "in": "body",
                "required": request_body.get("required", False),
                "type": body_schema.get("type"),
            }
        return parameters


class ComponentClient(DeviceClientMixin, BaseClient):
    """Device-semantic HTTP client — adds non-blocking concurrency guard to BaseClient."""

    def __init__(
        self,
        url: str | AnyHttpUrl,
        *,
        component_ui: str = "undefined",
        dry_run: bool = False,
        pool_json_log: Path | None = None,
        timeout_commands: str = "10 s",
        error_resilient: bool = False,
        cancellation_token=None,
        pause_event=None,
    ) -> None:
        BaseClient.__init__(self, url, dry_run=dry_run)
        self._init_device_semantics(
            component_ui=component_ui,
            dry_run=dry_run,
            pool_json_log=pool_json_log,
            timeout_commands=timeout_commands,
            error_resilient=error_resilient,
            cancellation_token=cancellation_token,
            pause_event=pause_event,
        )
        self._is_idle_supported: bool | None = None

    def _raise_for_status(self, response: requests.Response, *args, **kwargs) -> None:
        if not self._error_resilient:
            BaseClient._raise_for_status(self, response, *args, **kwargs)
            return
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            logger.error("Client HTTP error (error_resilient=True): {}", exc)
            _push_thread_resilient_error(exc)

    # ── transport hooks ───────────────────────────────────────────────────────
    # Call BaseClient's verb methods explicitly by class, never via bare
    # super() — this class's MRO is ComponentClient -> DeviceClientMixin ->
    # BaseClient, so `super().get(...)` from a method defined here would
    # resolve to DeviceClientMixin.get and recurse back into _call(). Calling
    # BaseClient.get/put/post explicitly also keeps tests that patch
    # `BaseClient.get`/`BaseClient.put` directly working unmodified.

    def _transport_get(self, path: str, *, params) -> CommandResponse:
        resp = BaseClient.get(self, path, params=params)
        return CommandResponse(native=resp, text=resp.text, body_fn=resp.json)

    def _transport_put(self, path: str, *, params, json) -> CommandResponse:
        resp = BaseClient.put(self, path, params=params, json=json)
        return CommandResponse(native=resp, text=resp.text, body_fn=resp.json)

    def _transport_post(self, path: str, *, params, json) -> CommandResponse:
        resp = BaseClient.post(self, path, params=params, json=json)
        return CommandResponse(native=resp, text=resp.text, body_fn=resp.json)

    # ── automatic wait-for-idle ─────────────────────────────────────────────
    # Every flowchem component exposes GET /is-idle (flowchem >= 1.1.3). A
    # put/post is a command that can make the device busy, so we block until
    # it reports idle again before returning — a get is a passive read and
    # can't make the device busy, so it never triggers this.

    def _execute_post_command(self, verb: str) -> None:
        if verb in ("put", "post") and not self._dry_run:
            self._wait_until_idle()

    def _wait_until_idle(self) -> None:
        if self._is_idle_supported is False:
            return
        deadline = (
            None
            if self._feedback_timeout is None
            else time.monotonic() + self._feedback_timeout
        )
        while True:
            if self._pause_event is not None and self._pause_event.is_set():
                paused_at = time.monotonic()
                self._wait_if_paused()
                # Time spent paused doesn't count against the idle-wait timeout.
                if deadline is not None:
                    deadline += time.monotonic() - paused_at
            self._raise_if_cancelled()
            try:
                response = BaseClient.get(self, _IS_IDLE_PATH)
            except requests.HTTPError as exc:
                response = exc.response

            if response is not None and response.status_code == 404:
                self._is_idle_supported = False
                logger.warning(
                    "{} ({}) does not expose GET /{} — update flowchem to "
                    ">= {} to enable automatic idle-wait after commands.",
                    self.component_ui,
                    self.base_url,
                    _IS_IDLE_PATH,
                    _MIN_FLOWCHEM_VERSION,
                )
                return

            self._is_idle_supported = True
            if response is not None and response.text.strip() == "true":
                return

            if deadline is not None and time.monotonic() >= deadline:
                timeout_exc = TimeoutError(
                    f"Device did not report idle within {self._feedback_timeout}s"
                )
                if self._error_resilient:
                    logger.error(
                        "Client timeout (error_resilient=True): {}", timeout_exc
                    )
                    _push_thread_resilient_error(timeout_exc)
                    return
                raise timeout_exc

            self._sleep_interruptibly(1.0)
