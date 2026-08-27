"""Unit tests for the custom routes extension point."""

from __future__ import annotations

import json

import pytest

from chemunited_workflow.api.services.custom_routes import (
    call_custom_route,
    discover_custom_routes,
    load_custom_routes,
)
from chemunited_workflow.custom_route_context import CustomRouteContext


@pytest.fixture(autouse=True)
def _reset_custom_route_context():
    yield
    CustomRouteContext.platform = None


def _write_hook(tmp_path, body: str) -> None:
    hook_dir = tmp_path / "customizations" / "routers"
    hook_dir.mkdir(parents=True, exist_ok=True)
    (hook_dir / "router_hook.py").write_text(body, encoding="utf-8")


def _write_associations(tmp_path, associations: list[dict] | None = None) -> None:
    (tmp_path / "connectivity").mkdir(parents=True, exist_ok=True)
    (tmp_path / "connectivity" / "associations.json").write_text(
        json.dumps({"associations": associations or []}), encoding="utf-8"
    )


# ── load_custom_routes ───────────────────────────────────────────────────────


def test_load_custom_routes_missing_file_returns_empty(tmp_path):
    assert load_custom_routes(tmp_path) == {}


def test_load_custom_routes_loads_registered_dict(tmp_path):
    _write_hook(tmp_path, "CUSTOM_ROUTES = {'double': lambda x: x * 2}\n")
    routes = load_custom_routes(tmp_path)
    assert set(routes) == {"double"}
    assert routes["double"](x=3) == 6


def test_load_custom_routes_missing_export_returns_empty(tmp_path):
    _write_hook(tmp_path, "NOT_THE_RIGHT_NAME = {}\n")
    assert load_custom_routes(tmp_path) == {}


def test_load_custom_routes_broken_file_returns_empty_without_raising(tmp_path):
    _write_hook(tmp_path, "raise RuntimeError('boom')\n")
    assert load_custom_routes(tmp_path) == {}


# ── discover_custom_routes ───────────────────────────────────────────────────


def test_discover_custom_routes_empty_when_no_hook(tmp_path):
    assert discover_custom_routes(tmp_path) == []


def test_discover_custom_routes_introspects_signature(tmp_path):
    _write_hook(
        tmp_path,
        "def purge(volume_ml, dry=False):\n"
        "    return volume_ml\n"
        "CUSTOM_ROUTES = {'purge': purge}\n",
    )
    [info] = discover_custom_routes(tmp_path)
    assert info["name"] == "purge"
    params = {p["name"]: p for p in info["parameters"]}
    assert params["volume_ml"]["required"] is True
    assert params["dry"]["required"] is False
    assert params["dry"]["default"] is False


def test_discover_custom_routes_skips_var_args_kwargs(tmp_path):
    _write_hook(
        tmp_path,
        "def anything(*args, **kwargs):\n"
        "    return None\n"
        "CUSTOM_ROUTES = {'anything': anything}\n",
    )
    [info] = discover_custom_routes(tmp_path)
    assert info["parameters"] == []


# ── call_custom_route ────────────────────────────────────────────────────────


def test_call_custom_route_unknown_name_raises_key_error(tmp_path):
    _write_associations(tmp_path)
    with pytest.raises(KeyError):
        call_custom_route(tmp_path, "missing", {})


def test_call_custom_route_success(tmp_path):
    _write_associations(tmp_path)
    _write_hook(tmp_path, "CUSTOM_ROUTES = {'double': lambda x: x * 2}\n")
    result = call_custom_route(tmp_path, "double", {"x": 3})
    assert result["name"] == "double"
    assert result["ok"] is True
    assert result["result"] == 6
    assert result["error"] is None
    assert result["latency_ms"] is not None


def test_call_custom_route_exception_is_captured_not_raised(tmp_path):
    _write_associations(tmp_path)
    _write_hook(
        tmp_path,
        "def boom():\n"
        "    raise ValueError('nope')\n"
        "CUSTOM_ROUTES = {'boom': boom}\n",
    )
    result = call_custom_route(tmp_path, "boom", {})
    assert result["ok"] is False
    assert result["result"] is None
    assert "nope" in result["error"]


def test_call_custom_route_sets_context_platform_during_call(tmp_path):
    _write_associations(tmp_path)
    _write_hook(
        tmp_path,
        "from chemunited_workflow import CustomRouteContext\n"
        "def check():\n"
        "    return CustomRouteContext.platform is not None\n"
        "CUSTOM_ROUTES = {'check': check}\n",
    )
    result = call_custom_route(tmp_path, "check", {})
    assert result["result"] is True
    assert CustomRouteContext.platform is None
