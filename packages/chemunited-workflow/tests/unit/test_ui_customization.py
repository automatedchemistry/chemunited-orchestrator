"""Unit tests for the dashboard customization hook (customizations/ui/ui_hook.py)."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from chemunited_workflow.api.services.ui_customization import (
    load_ui,
    resolve_extension_file,
)
from chemunited_workflow.ui import UI_API_VERSION, ActionField


def _ui(tmp_path: Path) -> Path:
    path = tmp_path / "customizations" / "ui"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_hook(tmp_path: Path, body: str) -> None:
    source = "from chemunited_workflow.ui import *\n" + textwrap.dedent(body)
    (_ui(tmp_path) / "ui_hook.py").write_text(source, encoding="utf-8")


def _write_file(tmp_path: Path, relative: str, text: str = "") -> None:
    path = _ui(tmp_path) / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_routes(tmp_path: Path, body: str) -> None:
    hook_dir = tmp_path / "customizations" / "routers"
    hook_dir.mkdir(parents=True, exist_ok=True)
    (hook_dir / "router_hook.py").write_text(textwrap.dedent(body), encoding="utf-8")


def _messages(manifest: dict) -> list[str]:
    return [error["message"] for error in manifest["errors"]]


# ── Loading ───────────────────────────────────────────────────────────────────


def test_no_project_customizes_nothing():
    manifest = load_ui(None).manifest
    assert manifest["active"] is False
    assert manifest["ui_api"] == UI_API_VERSION
    assert manifest["pages"] == []
    assert manifest["errors"] == []


def test_no_hook_customizes_nothing(tmp_path):
    manifest = load_ui(tmp_path).manifest
    assert manifest["active"] is False
    assert manifest["override_active"] is False
    assert manifest["errors"] == []


def test_full_override_is_reported(tmp_path):
    _write_file(tmp_path, "dist/index.html", "<html></html>")
    assert load_ui(tmp_path).manifest["override_active"] is True


def test_brand_theme_and_page(tmp_path):
    _write_file(tmp_path, "assets/logo.svg", "<svg/>")
    _write_file(tmp_path, "theme.css", ":root {}")
    _write_file(tmp_path, "pages/Sensors.vue", "<template><p/></template>")
    _write_hook(
        tmp_path,
        """
        DASHBOARD = Dashboard(
            brand=Brand(title="Flow Lab", monogram="FL", logo="assets/logo.svg"),
            theme_css="theme.css",
            pages=[VuePage(path="/sensors", label="Sensors",
                           component="pages/Sensors.vue", after="/monitoring")],
        )
        """,
    )
    manifest = load_ui(tmp_path).manifest
    assert manifest["errors"] == []
    assert manifest["active"] is True
    assert manifest["brand"] == {
        "title": "Flow Lab",
        "subtitle": None,
        "monogram": "FL",
        "logo_url": "/ui/ext/assets/logo.svg",
    }
    assert manifest["theme_css_url"] == "/ui/ext/theme.css"
    assert manifest["pages"] == [
        {
            "path": "/sensors",
            "label": "Sensors",
            "icon_url": None,
            "after": "/monitoring",
            "hidden": False,
            "replaces": False,
            "kind": "vue",
            "component": "pages/Sensors.vue",
            "component_url": "/ui/ext/pages/Sensors.vue",
        }
    ]


def test_hook_syntax_error_reports_its_line(tmp_path):
    _write_hook(tmp_path, "DASHBOARD = Dashboard(\n")
    manifest = load_ui(tmp_path).manifest
    [error] = manifest["errors"]
    assert manifest["active"] is True
    assert error["source"] == "ui_hook.py"
    assert error["message"].startswith("SyntaxError")
    assert isinstance(error["line"], int)


def test_hook_without_dashboard_is_reported(tmp_path):
    _write_hook(tmp_path, "X = 1\n")
    assert "must define DASHBOARD" in _messages(load_ui(tmp_path).manifest)[0]


def test_validation_error_names_the_field_and_line(tmp_path):
    _write_hook(
        tmp_path, "DASHBOARD = Dashboard(pages=[VuePage(path='/a', label='A')])\n"
    )
    [error] = load_ui(tmp_path).manifest["errors"]
    assert "component: Field required" in error["message"]
    assert error["line"] == 2


def test_a_bad_entry_is_skipped_and_the_rest_applies(tmp_path):
    _write_file(tmp_path, "pages/Good.vue")
    _write_hook(
        tmp_path,
        """
        DASHBOARD = Dashboard(pages=[
            VuePage(path="/missing", label="Missing", component="pages/Missing.vue"),
            VuePage(path="/good", label="Good", component="pages/Good.vue"),
        ])
        """,
    )
    manifest = load_ui(tmp_path).manifest
    assert [page["path"] for page in manifest["pages"]] == ["/good"]
    assert "'pages/Missing.vue' was not found" in _messages(manifest)[0]


@pytest.mark.parametrize(
    ("path", "message"),
    [
        ("/Sensors", "one segment"),
        ("/a/b", "one segment"),
        ("/run", "reserved"),
        ("/customizations", "reserved"),
        ("/protocols", "set replaces=True"),
    ],
)
def test_page_path_rules(tmp_path, path, message):
    _write_file(tmp_path, "P.vue")
    _write_hook(
        tmp_path,
        f"DASHBOARD = Dashboard(pages=[VuePage(path={path!r}, label='P', component='P.vue')])\n",
    )
    manifest = load_ui(tmp_path).manifest
    assert manifest["pages"] == []
    assert message in _messages(manifest)[0]


def test_replacing_a_built_in_page(tmp_path):
    _write_file(tmp_path, "P.vue")
    _write_hook(
        tmp_path,
        """
        DASHBOARD = Dashboard(pages=[
            VuePage(path="/protocols", label="Protocols", component="P.vue", replaces=True),
            VuePage(path="/extra", label="Extra", component="P.vue", replaces=True),
            VuePage(path="/protocols", label="Again", component="P.vue", replaces=True),
        ])
        """,
    )
    manifest = load_ui(tmp_path).manifest
    assert [page["path"] for page in manifest["pages"]] == ["/protocols"]
    assert manifest["pages"][0]["replaces"] is True
    messages = _messages(manifest)
    assert "'/extra' is not a built-in page" in messages[0]
    assert "another page already uses this path" in messages[1]


def test_after_must_name_a_page(tmp_path):
    _write_file(tmp_path, "P.vue")
    _write_hook(
        tmp_path,
        "DASHBOARD = Dashboard(pages=[VuePage(path='/p', label='P', component='P.vue', "
        "after='/nowhere')])\n",
    )
    manifest = load_ui(tmp_path).manifest
    assert manifest["pages"][0]["after"] is None
    assert "after='/nowhere' names no page" in _messages(manifest)[0]


def test_nav_changes_only_built_in_entries(tmp_path):
    _write_hook(
        tmp_path,
        """
        DASHBOARD = Dashboard(nav=[
            NavItem(path="/logs", label="Run logs", order=5),
            NavItem(path="/sensors", hidden=True),
        ])
        """,
    )
    manifest = load_ui(tmp_path).manifest
    assert manifest["nav"] == [
        {
            "path": "/logs",
            "label": "Run logs",
            "hidden": False,
            "order": 5,
            "icon_url": None,
        }
    ]
    assert "nav entries change built-in pages" in _messages(manifest)[0]


def test_widget_in_a_slot(tmp_path):
    _write_file(tmp_path, "widgets/Card.vue")
    _write_hook(
        tmp_path,
        "DASHBOARD = Dashboard(widgets=[Widget(slot='dashboard.cards', "
        "component='widgets/Card.vue', title='Reactor')])\n",
    )
    assert load_ui(tmp_path).manifest["widgets"] == [
        {
            "slot": "dashboard.cards",
            "component": "widgets/Card.vue",
            "component_url": "/ui/ext/widgets/Card.vue",
            "title": "Reactor",
            "order": 0,
        }
    ]


def test_unknown_slot_suggests_the_closest(tmp_path):
    _write_file(tmp_path, "W.vue")
    _write_hook(
        tmp_path,
        "DASHBOARD = Dashboard(widgets=[Widget(slot='dashbord.cards', component='W.vue')])\n",
    )
    manifest = load_ui(tmp_path).manifest
    assert manifest["widgets"] == []
    assert "did you mean 'dashboard.cards'?" in _messages(manifest)[0]


def test_html_page(tmp_path):
    _write_hook(
        tmp_path,
        "DASHBOARD = Dashboard(pages=[HtmlPage(path='/report', label='Report', "
        "render=lambda: '<p>hi</p>', refresh_seconds=30)])\n",
    )
    loaded = load_ui(tmp_path)
    [page] = loaded.manifest["pages"]
    assert page["kind"] == "html"
    assert page["html_url"] == "/ui/html/report"
    assert page["refresh_seconds"] == 30
    assert loaded.html_pages["/report"].render() == "<p>hi</p>"


def test_newer_ui_api_is_reported(tmp_path):
    _write_hook(
        tmp_path, f"DASHBOARD = Dashboard(requires_ui_api={UI_API_VERSION + 1})\n"
    )
    manifest = load_ui(tmp_path).manifest
    assert manifest["requires_ui_api"] == UI_API_VERSION + 1
    assert "update chemunited-workflow" in _messages(manifest)[0]


# ── Page actions ──────────────────────────────────────────────────────────────

_SAVE_ROUTE = """
from typing import Literal

def save(logs: list[str], username: str, retries: int = 3,
         mode: Literal["a", "b"] = "a", note: str | None = None):
    '''Save the runs somewhere.'''
    return len(logs)

CUSTOM_ROUTES = {"save": save}
"""


def test_action_form_comes_from_the_routes_type_hints(tmp_path):
    _write_routes(tmp_path, _SAVE_ROUTE)
    _write_hook(
        tmp_path,
        """
        DASHBOARD = Dashboard(actions=[PageAction(
            page="export", route="save", label="Save", context={"logs": "selection"},
            fields=[ActionField("username", label="User", placeholder="name", remember=True),
                    ActionField("note", hidden=True)],
        )])
        """,
    )
    manifest = load_ui(tmp_path).manifest
    assert manifest["errors"] == []
    [action] = manifest["actions"]
    assert action["id"] == "export:0"
    assert action["description"] == "Save the runs somewhere."
    assert action["context"] == {"logs": "selection"}
    assert action["required"] == ["username"]
    assert action["remember"] == ["username"]
    assert action["properties"] == {
        "username": {"type": "string", "title": "User", "placeholder": "name"},
        "retries": {"type": "integer", "title": "Retries", "default": 3},
        "mode": {"type": "string", "enum": ["a", "b"], "title": "Mode", "default": "a"},
    }


@pytest.mark.parametrize(
    ("action", "message"),
    [
        (
            "PageAction(page='export', route='nope', label='X')",
            "no custom route 'nope'",
        ),
        ("PageAction(page='logs', route='save', label='X')", "actions can go on"),
        (
            "PageAction(page='export', route='save', label='X', context={'other': 'selection'})",
            "context names 'other'",
        ),
        (
            "PageAction(page='export', route='save', label='X', context={'logs': 'run_id'})",
            "offers selection, not 'run_id'",
        ),
        (
            "PageAction(page='export', route='save', label='X', fields=[ActionField('zzz')])",
            "'zzz' is not a parameter",
        ),
        (
            "PageAction(page='export', route='save', label='X', "
            "fields=[ActionField('username', hidden=True)])",
            "hidden but has no default",
        ),
    ],
)
def test_action_errors(tmp_path, action, message):
    _write_routes(tmp_path, _SAVE_ROUTE)
    _write_hook(tmp_path, f"DASHBOARD = Dashboard(actions=[{action}])\n")
    manifest = load_ui(tmp_path).manifest
    assert manifest["actions"] == []
    assert message in _messages(manifest)[0]


def test_action_field_takes_its_name_positionally():
    assert ActionField("username").name == "username"
    assert ActionField(name="note", hidden=True).hidden is True


# ── resolve_extension_file ────────────────────────────────────────────────────


def test_resolve_extension_file_allows_known_files_in_subfolders(tmp_path):
    _write_file(tmp_path, "data/figures/a.png")
    resolved = resolve_extension_file(tmp_path, "data/figures/a.png")
    assert resolved == (_ui(tmp_path) / "data" / "figures" / "a.png").resolve()


@pytest.mark.parametrize(
    "relative",
    [
        "ui_hook.py",
        "../secret.vue",
        "dist/assets/a.js",
        "__pycache__/a.js",
        ".hidden/a.js",
        "missing.vue",
        "/etc/a.vue",
    ],
)
def test_resolve_extension_file_refuses(tmp_path, relative):
    _write_file(tmp_path, "ui_hook.py")
    _write_file(tmp_path, "dist/assets/a.js")
    _write_file(tmp_path, "__pycache__/a.js")
    _write_file(tmp_path, ".hidden/a.js")
    (tmp_path / "customizations" / "secret.vue").write_text("", encoding="utf-8")
    assert resolve_extension_file(tmp_path, relative) is None
