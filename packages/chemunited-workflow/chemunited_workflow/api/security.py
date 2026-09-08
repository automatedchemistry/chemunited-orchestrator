"""Pure-ASGI loopback-or-token gate for state-changing requests.

Monitoring/read access (``GET``/``HEAD``/``OPTIONS``) is always open to
whoever can reach the server. State-changing requests (``POST``/``PUT``/
``DELETE``/...) are allowed unconditionally from loopback, and from any other
address only with a valid bearer token.
"""

from __future__ import annotations

import ipaddress
import secrets

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _is_loopback(client: tuple[str, int] | None) -> bool:
    if client is None:
        return False
    try:
        return ipaddress.ip_address(client[0]).is_loopback
    except ValueError:
        return False


def _bearer_token(header_value: str | None) -> str | None:
    if header_value is None:
        return None
    scheme, _, value = header_value.partition(" ")
    if scheme.lower() != "bearer" or not value:
        return None
    return value


class AccessControlMiddleware:
    """Gate state-changing requests behind loopback-or-token.

    Implemented as pure ASGI (not ``BaseHTTPMiddleware``) so safe-method
    requests -- including SSE streams like ``GET /run/stream`` -- pass
    straight through to the inner app with no response wrapping.
    """

    def __init__(self, app: ASGIApp, *, token: str | None = None) -> None:
        self.app = app
        self._token = (token or "").strip() or None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] in _SAFE_METHODS:
            await self.app(scope, receive, send)
            return

        if _is_loopback(scope.get("client")):
            await self.app(scope, receive, send)
            return

        presented = _bearer_token(Headers(scope=scope).get("authorization"))
        if (
            self._token is not None
            and presented is not None
            and secrets.compare_digest(presented, self._token)
        ):
            await self.app(scope, receive, send)
            return

        response = JSONResponse(
            {"detail": "Remote write access requires a valid bearer token."},
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
        )
        await response(scope, receive, send)
