"""Integration tests for the dashboard customization routes (/ui/...) and the
dashboard's fallback for unknown page URLs."""

from __future__ import annotations

import importlib.util
import sys
import textwrap
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from tests.helpers import LOOPBACK_CLIENT, make_project_tree

from chemunited_workflow.api import create_api

HTML = {"Accept": "text/html,application/xhtml+xml"}


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def project(tmp_path):
    make_project_tree(tmp_path)
    return tmp_path


@pytest.fixture
def app(project):
    from chemunited_workflow.api.dependencies import get_project_holder
    from chemunited_workflow.project_loader import ProjectModules

    proc_dir = project / "processes"
    mod = _load_module(proc_dir / "my_process.py", "my_process_ui_api")
    main_mod = _load_module(proc_dir / "main_parameters.py", "main_parameters_ui_api")
    api = create_api()
    holder = api.dependency_overrides[get_project_holder]()
    holder.load(
        ProjectModules(
            project_dir=project,
            processes={"my_process": mod.MyProcess},
            configs={"my_process": mod.MyConfig},
            main_parameter_class=main_mod.MainParameter,
        )
    )
    return api


@pytest.fixture
def client(app):
    return TestClient(app, client=LOOPBACK_CLIENT)


def _write(project: Path, relative: str, text: str = "") -> Path:
    path = project / "customizations" / "ui" / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _write_hook(project: Path, body: str) -> None:
    _write(
        project,
        "ui_hook.py",
        "from chemunited_workflow.ui import *\n" + textwrap.dedent(body),
    )


# ── /ui/manifest ──────────────────────────────────────────────────────────────


def test_manifest_without_a_project():
    r = TestClient(create_api(), client=LOOPBACK_CLIENT).get("/ui/manifest")
    assert r.status_code == 200
    assert r.json()["active"] is False
    assert r.headers["cache-control"] == "no-store"


def test_manifest_lists_the_hooks_pages(client, project):
    _write(project, "pages/Sensors.vue", "<template><p/></template>")
    _write_hook(
        project,
        "DASHBOARD = Dashboard(pages=[VuePage(path='/sensors', label='Sensors', "
        "component='pages/Sensors.vue')])\n",
    )
    body = client.get("/ui/manifest").json()
    assert body["active"] is True
    assert body["errors"] == []
    assert body["pages"][0]["component_url"] == "/ui/ext/pages/Sensors.vue"


def test_manifest_is_open_to_remote_viewers(app):
    assert TestClient(app).get("/ui/manifest").status_code == 200


# ── /ui/ext ───────────────────────────────────────────────────────────────────


def test_ext_serves_a_vue_file_as_text_and_revalidates(client, project):
    _write(project, "pages/Sensors.vue", "<template><p/></template>")
    r = client.get("/ui/ext/pages/Sensors.vue")
    assert r.status_code == 200
    assert r.text == "<template><p/></template>"
    assert r.headers["content-type"].startswith("text/plain")
    assert r.headers["cache-control"] == "no-cache"
    etag = r.headers["etag"]

    again = client.get("/ui/ext/pages/Sensors.vue", headers={"If-None-Match": etag})
    assert again.status_code == 304


def test_ext_serves_javascript_with_its_type(client, project):
    _write(project, "vendor/lib.js", "export const x = 1")
    r = client.get("/ui/ext/vendor/lib.js")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/javascript")


@pytest.mark.parametrize(
    "path",
    [
        "ui_hook.py",
        "%2E%2E%2Fsecret.vue",
        "dist/assets/a.js",
        "__pycache__/a.js",
        "missing.vue",
    ],
)
def test_ext_refuses(client, project, path):
    _write_hook(project, "DASHBOARD = Dashboard()\n")
    _write(project, "dist/assets/a.js")
    _write(project, "__pycache__/a.js")
    (project / "customizations" / "secret.vue").write_text("", encoding="utf-8")
    assert client.get(f"/ui/ext/{path}").status_code == 404


def test_ext_without_a_project():
    r = TestClient(create_api(), client=LOOPBACK_CLIENT).get("/ui/ext/a.vue")
    assert r.status_code == 404


# ── Fallback for unknown pages ────────────────────────────────────────────────


def test_unknown_page_gets_the_dashboard(client):
    r = client.get("/sensors", headers=HTML)
    assert r.status_code == 200
    assert '<div id="app"></div>' in r.text
    assert r.headers["cache-control"] == "no-store"


def test_unknown_page_gets_the_projects_full_override(client, project):
    _write(
        project, "dist/index.html", "<html><body>CUSTOM DASHBOARD MARKER</body></html>"
    )
    r = client.get("/sensors", headers=HTML)
    assert "CUSTOM DASHBOARD MARKER" in r.text


@pytest.mark.parametrize(
    ("path", "headers"),
    [
        ("/sensors", {"Accept": "application/json"}),
        ("/nested/page", HTML),
        ("/missing.js", HTML),
        ("/assets/missing.js", HTML),
    ],
)
def test_other_misses_stay_404(client, path, headers):
    assert client.get(path, headers=headers).status_code == 404


# ── /ui/html ──────────────────────────────────────────────────────────────────


def test_html_page_renders_sandboxed(client, project):
    _write_hook(
        project,
        "DASHBOARD = Dashboard(pages=[HtmlPage(path='/report', label='Report', "
        "render=lambda: '<p>report body</p>')])\n",
    )
    r = client.get("/ui/html/report")
    assert r.status_code == 200
    assert r.text == "<p>report body</p>"
    assert r.headers["content-security-policy"] == "sandbox allow-scripts"


def test_html_page_that_raises_is_a_500_with_the_error(client, project):
    _write_hook(
        project,
        """
        def broken():
            raise ValueError("<no data>")

        DASHBOARD = Dashboard(pages=[HtmlPage(path='/report', label='Report', render=broken)])
        """,
    )
    r = client.get("/ui/html/report")
    assert r.status_code == 500
    assert "ValueError: &lt;no data&gt;" in r.text


def test_unknown_html_page_is_404(client):
    assert client.get("/ui/html/nothing").status_code == 404
