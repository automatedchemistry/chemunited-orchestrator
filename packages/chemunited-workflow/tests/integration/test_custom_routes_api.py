"""Integration tests for the /custom routes."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from chemunited_workflow.api import create_api
from tests.helpers import make_project_tree

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _write_hook(tmp_path: Path, body: str) -> None:
    hook_dir = tmp_path / "customizations" / "routers"
    hook_dir.mkdir(parents=True, exist_ok=True)
    (hook_dir / "router_hook.py").write_text(body, encoding="utf-8")


@pytest.fixture
def project(tmp_path):
    dirs = make_project_tree(tmp_path)
    (dirs["connectivity_dir"] / "associations.json").write_text(
        (FIXTURES / "associations.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return {"dirs": dirs, "tmp_path": tmp_path}


def _make_app_with_project(project):
    from chemunited_workflow.api.dependencies import get_project_holder
    from chemunited_workflow.project_loader import ProjectModules

    proc_dir = project["dirs"]["process_dir"]
    mod = _load_module(proc_dir / "my_process.py", "my_process_custom_routes")
    main_mod = _load_module(
        proc_dir / "main_parameters.py", "main_parameters_custom_routes"
    )

    api = create_api()
    holder = api.dependency_overrides[get_project_holder]()
    holder.load(
        ProjectModules(
            project_dir=project["tmp_path"],
            processes={"my_process": mod.MyProcess},
            configs={"my_process": mod.MyConfig},
            main_parameter_class=main_mod.MainParameter,
        )
    )
    return api


@pytest.fixture
def app(project):
    return _make_app_with_project(project)


@pytest.fixture
def client(app):
    return TestClient(app)


# ── no project loaded ────────────────────────────────────────────────────────


def test_discover_returns_503_when_no_project_loaded():
    client = TestClient(create_api())
    r = client.get("/custom/discover")
    assert r.status_code == 503


def test_call_returns_503_when_no_project_loaded():
    client = TestClient(create_api())
    r = client.post("/custom/anything", json={})
    assert r.status_code == 503


# ── /custom/discover ─────────────────────────────────────────────────────────


def test_discover_empty_when_no_hook_file(client):
    r = client.get("/custom/discover")
    assert r.status_code == 200
    assert r.json() == []


def test_discover_lists_registered_routes(client, project):
    _write_hook(
        project["tmp_path"],
        "def double(x):\n" "    return x * 2\n" "CUSTOM_ROUTES = {'double': double}\n",
    )
    r = client.get("/custom/discover")
    assert r.status_code == 200
    [info] = r.json()
    assert info["name"] == "double"
    assert info["parameters"] == [{"name": "x", "required": True, "default": None}]


# ── POST /custom/{name} ──────────────────────────────────────────────────────


def test_call_unknown_route_returns_404(client):
    r = client.post("/custom/missing", json={})
    assert r.status_code == 404


def test_call_route_success(client, project):
    _write_hook(
        project["tmp_path"],
        "def double(x):\n" "    return x * 2\n" "CUSTOM_ROUTES = {'double': double}\n",
    )
    r = client.post("/custom/double", json={"x": 3})
    assert r.status_code == 200
    body = r.json()
    assert body == {
        "name": "double",
        "ok": True,
        "result": 6,
        "error": None,
        "latency_ms": body["latency_ms"],
    }


def test_call_route_exception_returns_200_with_ok_false(client, project):
    _write_hook(
        project["tmp_path"],
        "def boom():\n"
        "    raise ValueError('nope')\n"
        "CUSTOM_ROUTES = {'boom': boom}\n",
    )
    r = client.post("/custom/boom", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "nope" in body["error"]
