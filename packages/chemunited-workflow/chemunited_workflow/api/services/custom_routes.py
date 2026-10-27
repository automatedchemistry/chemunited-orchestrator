"""Custom routes — project-defined named actions, registered via
``{project_dir}/customizations/routers/router_hook.py``.

See docs/api-reference.md#custom-routes.
"""

from __future__ import annotations

import importlib.util
import inspect
import time
from pathlib import Path
from typing import Any, Callable

from loguru import logger
from pydantic import TypeAdapter

from ...command_events import CommandObserver
from ...custom_route_context import CustomRouteContext
from ...platform import Platform


def _safe_close(client: Any, component_name: str) -> None:
    """Best-effort cleanup for a throwaway client — never masks the caller's result."""
    try:
        client.close()
    except Exception as exc:
        logger.warning(
            "Failed to close throwaway client for '{}': {}", component_name, exc
        )


def load_custom_routes(project_dir: Path) -> dict[str, Callable[..., Any]]:
    """Load CUSTOM_ROUTES from the project's router hook file, if any.

    Never raises: a missing file yields an empty registry silently (custom
    routes are optional); a file that fails to import or doesn't export a
    CUSTOM_ROUTES dict is logged and also yields an empty registry — a
    broken hook must never take the endpoint down, matching the same
    "a hook failure must never abort the caller" principle used for
    monitoring's CUSTOM_SOURCES.
    """
    path = project_dir / "customizations" / "routers" / "router_hook.py"
    if not path.exists():
        return {}
    try:
        spec = importlib.util.spec_from_file_location("router_hook", path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot create a module spec from {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        routes = getattr(module, "CUSTOM_ROUTES", None)
        if not isinstance(routes, dict):
            raise AttributeError("router_hook.py does not export a CUSTOM_ROUTES dict")
        return routes
    except Exception:
        logger.exception("Failed to load custom routes from {}", path)
        return {}


def _signature(func: Callable[..., Any]) -> inspect.Signature | None:
    """The function's signature, with string annotations (``from __future__
    import annotations``) resolved where possible."""
    try:
        return inspect.signature(func, eval_str=True)
    except Exception:
        # An annotation that doesn't evaluate (say, a name imported only under
        # TYPE_CHECKING): keep the annotations as strings instead.
        try:
            return inspect.signature(func)
        except (TypeError, ValueError):
            return None


def _json_schema(annotation: Any) -> dict[str, Any]:
    """JSON schema for a parameter's type hint; empty when there is none or it
    can't be described (an arbitrary class, an unresolved string)."""
    if annotation is inspect.Parameter.empty or isinstance(annotation, str):
        return {}
    try:
        return TypeAdapter(annotation).json_schema()
    except Exception:
        return {}


def _summary(func: Callable[..., Any]) -> str | None:
    """First paragraph of the function's docstring."""
    doc = inspect.getdoc(func)
    if not doc:
        return None
    return " ".join(doc.split("\n\n", 1)[0].split())


def discover_custom_routes(project_dir: Path) -> list[dict[str, Any]]:
    """List the registered custom routes, with parameter hints introspected
    from each function's signature: whether each parameter is required, its
    default, and a JSON schema built from its type hint."""
    routes = load_custom_routes(project_dir)
    result = []
    for name, func in routes.items():
        parameters: list[dict[str, Any]] = []
        sig = _signature(func)
        if sig is not None:
            for pname, param in sig.parameters.items():
                if param.kind in (
                    inspect.Parameter.VAR_POSITIONAL,
                    inspect.Parameter.VAR_KEYWORD,
                ):
                    continue
                has_default = param.default is not inspect.Parameter.empty
                parameters.append(
                    {
                        "name": pname,
                        "required": not has_default,
                        "default": param.default if has_default else None,
                        "json_schema": _json_schema(param.annotation),
                    }
                )
        result.append(
            {"name": name, "description": _summary(func), "parameters": parameters}
        )
    return result


def call_custom_route(
    project_dir: Path,
    name: str,
    kwargs: dict[str, Any],
    *,
    command_observer: CommandObserver | None = None,
) -> dict[str, Any]:
    """Call a registered custom route by name.

    Raises KeyError if `name` isn't registered — the caller (router/MCP
    tool) turns that into a 404 / error response. Once the function is
    found, it never lets that function's own exception propagate: a raised
    exception is captured into the result as `ok=False, error=...`, the
    same "the call itself succeeded, the action failed" contract
    `send_component_command` uses for a device call.

    Opens a throwaway, unlocked Platform for the call's duration, exposed
    to the function via `CustomRouteContext.platform` so it can reach a
    real device — closed again once the call returns. ``command_observer``
    puts the commands it sends on the live platform view.
    """
    routes = load_custom_routes(project_dir)
    if name not in routes:
        raise KeyError(f"Custom route '{name}' is not registered.")
    func = routes[name]

    platform = Platform.from_project_dir(
        project_dir, error_resilient=True, command_observer=command_observer
    )
    CustomRouteContext.platform = platform
    start = time.monotonic()
    try:
        result = func(**kwargs)
        ok, error = True, None
    except Exception as exc:
        result, ok, error = None, False, str(exc)
    finally:
        CustomRouteContext.platform = None
        for component_name, client in platform.items():
            _safe_close(client, component_name)
    latency_ms = round((time.monotonic() - start) * 1000)

    return {
        "name": name,
        "ok": ok,
        "result": result,
        "error": error,
        "latency_ms": latency_ms,
    }
