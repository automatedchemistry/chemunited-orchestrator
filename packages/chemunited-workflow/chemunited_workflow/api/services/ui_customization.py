"""Dashboard customization: loads ``{project_dir}/customizations/ui/ui_hook.py``
and turns its ``DASHBOARD`` into the manifest the dashboard applies at start-up
(``GET /ui/manifest``), and resolves the files under ``customizations/ui/`` the
browser may fetch (``GET /ui/ext/{path}``).

Like the other hooks, loading never raises. A missing hook means no
customization. A hook that fails to import, or an entry that doesn't check out,
is reported in the manifest's ``errors`` (and logged) while every other entry
still applies. See docs/html-ui.md#runtime-customizations.
"""

from __future__ import annotations

import difflib
import importlib.util
import json
import re
import traceback
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from loguru import logger
from pydantic import ValidationError

from ...ui.models import (
    ACTION_PAGES,
    BUILTIN_PAGES,
    SLOTS,
    UI_API_VERSION,
    ActionField,
    Dashboard,
    HtmlPage,
    PageAction,
    VuePage,
)
from .custom_routes import discover_custom_routes

HOOK_FILENAME = "ui_hook.py"

# What GET /ui/ext/{path} serves from customizations/ui/, by suffix.
EXTENSION_CONTENT_TYPES: dict[str, str] = {
    ".vue": "text/plain; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".json": "application/json",
    ".csv": "text/csv; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".woff2": "font/woff2",
}
_IMAGE_SUFFIXES = (".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp")

# A custom page path is one lowercase segment, so it can't shadow the API.
_PAGE_PATH = re.compile(r"^/[a-z0-9][a-z0-9-]*$")
_RESERVED_PATHS = frozenset(
    {
        "/assets",
        "/components",
        "/custom",
        "/customizations",
        "/docs",
        "/mcp",
        "/platform",
        "/processes",
        "/project",
        "/project-static",
        "/redoc",
        "/run",
        "/ui",
    }
)
_FORM_TYPES = frozenset({"string", "integer", "number", "boolean", "array"})


def ui_dir(project_dir: Path) -> Path:
    return project_dir / "customizations" / "ui"


def full_override_active(project_dir: Path) -> bool:
    """Whether the project ships a whole prebuilt dashboard (``ui/dist``), which
    wins over the bundled one and so over runtime customization."""
    return (ui_dir(project_dir) / "dist" / "index.html").is_file()


def resolve_extension_file(project_dir: Path, relative: str) -> Path | None:
    """The file ``GET /ui/ext/{relative}`` may serve, or None.

    Only files under ``customizations/ui/`` with a known suffix; never hidden
    files, ``__pycache__`` or the ``dist/`` override (served on its own).
    """
    posix = PurePosixPath(relative.replace("\\", "/"))
    if not posix.parts or posix.parts[0] in ("dist", "/"):
        return None
    if any(part.startswith(".") or part == "__pycache__" for part in posix.parts):
        return None
    if posix.suffix.lower() not in EXTENSION_CONTENT_TYPES:
        return None
    base = ui_dir(project_dir).resolve()
    candidate = (base / posix).resolve()
    if not candidate.is_relative_to(base) or not candidate.is_file():
        return None
    return candidate


@dataclass
class LoadedUi:
    manifest: dict[str, Any]
    # HtmlPage entries by page path, for GET /ui/html/{path}.
    html_pages: dict[str, HtmlPage] = field(default_factory=dict)


def _empty_manifest(project_dir: Path | None) -> dict[str, Any]:
    return {
        "ui_api": UI_API_VERSION,
        "requires_ui_api": UI_API_VERSION,
        # A ui_hook.py exists for the loaded project.
        "active": False,
        "override_active": project_dir is not None
        and full_override_active(project_dir),
        "brand": None,
        "theme_css_url": None,
        "pages": [],
        "nav": [],
        "actions": [],
        "widgets": [],
        "protocols": {"process_categories": {}, "other_label": "Other"},
        "slots": dict(SLOTS),
        "errors": [],
    }


def _error(source: str, message: str, line: int | None = None) -> dict[str, Any]:
    return {"source": source, "line": line, "message": message}


def _hook_error(exc: BaseException, path: Path) -> dict[str, Any]:
    """Describe a ui_hook.py that failed to import, with the line it failed on."""
    if isinstance(exc, SyntaxError):
        return _error(HOOK_FILENAME, f"SyntaxError: {exc.msg}", exc.lineno)
    line = None
    for frame in traceback.extract_tb(exc.__traceback__):
        if Path(frame.filename).resolve() == path.resolve():
            line = frame.lineno
    if isinstance(exc, ValidationError):
        problems = "; ".join(
            f"{'.'.join(str(part) for part in err['loc']) or exc.title}: {err['msg']}"
            for err in exc.errors()
        )
        message = f"{exc.title}: {problems}"
    else:
        message = f"{type(exc).__name__}: {exc}"
    return _error(HOOK_FILENAME, message, line)


def _import_dashboard(path: Path) -> Dashboard:
    spec = importlib.util.spec_from_file_location("ui_hook", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot create a module spec from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    dashboard = getattr(module, "DASHBOARD", None)
    if not isinstance(dashboard, Dashboard):
        raise TypeError("ui_hook.py must define DASHBOARD = Dashboard(...)")
    return dashboard


def load_ui(project_dir: Path | None) -> LoadedUi:
    """Load the project's dashboard customization. Never raises."""
    manifest = _empty_manifest(project_dir)
    if project_dir is None:
        return LoadedUi(manifest)
    path = ui_dir(project_dir) / HOOK_FILENAME
    if not path.is_file():
        return LoadedUi(manifest)
    manifest["active"] = True
    try:
        dashboard = _import_dashboard(path)
    except Exception as exc:
        logger.exception("Failed to load the dashboard customization from {}", path)
        manifest["errors"].append(_hook_error(exc, path))
        return LoadedUi(manifest)
    return _ManifestBuilder(project_dir, dashboard, manifest).build()


# ── Action forms ──────────────────────────────────────────────────────────────


def _humanize(name: str) -> str:
    words = name.replace("_", " ").strip()
    return words[:1].upper() + words[1:]


def _is_json(value: Any) -> bool:
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return False
    return True


def _without_null(schema: dict[str, Any]) -> dict[str, Any]:
    """Collapse ``X | None`` (an anyOf with a null branch) to X's schema."""
    for key in ("anyOf", "oneOf"):
        options = schema.get(key)
        if not isinstance(options, list):
            continue
        rest = [
            o for o in options if not (isinstance(o, dict) and o.get("type") == "null")
        ]
        if len(rest) == 1 and isinstance(rest[0], dict):
            outer = {k: v for k, v in schema.items() if k != key}
            return {**rest[0], **outer}
    return schema


def _form_property(param: dict[str, Any], field: ActionField | None) -> dict[str, Any]:
    """One SchemaForm-style property for a route parameter, from its type hint."""
    schema = _without_null(param.get("json_schema") or {})
    kind = schema.get("type")
    prop: dict[str, Any] = {"type": kind if kind in _FORM_TYPES else "string"}
    if "enum" in schema:
        prop["enum"] = list(schema["enum"])
    elif "const" in schema:
        prop["enum"] = [schema["const"]]
    if prop["type"] == "array":
        items = schema.get("items")
        item_type = items.get("type") if isinstance(items, dict) else None
        prop["items"] = {"type": item_type if item_type in _FORM_TYPES else "string"}
    for key in ("minimum", "maximum", "minLength", "maxLength", "description"):
        if key in schema:
            prop[key] = schema[key]
    label = field.label if field is not None else None
    prop["title"] = label or schema.get("title") or _humanize(param["name"])
    if not param["required"] and _is_json(param.get("default")):
        prop["default"] = param["default"]
    if field is not None and field.placeholder:
        prop["placeholder"] = field.placeholder
    return prop


# ── Manifest ──────────────────────────────────────────────────────────────────


class _ManifestBuilder:
    """Checks each DASHBOARD entry and adds the ones that pass to the manifest."""

    def __init__(
        self, project_dir: Path, dashboard: Dashboard, manifest: dict[str, Any]
    ) -> None:
        self._project_dir = project_dir
        self._dashboard = dashboard
        self._manifest = manifest
        self._html_pages: dict[str, HtmlPage] = {}

    def build(self) -> LoadedUi:
        dashboard = self._dashboard
        self._manifest["requires_ui_api"] = dashboard.requires_ui_api
        if dashboard.requires_ui_api > UI_API_VERSION:
            self._error(
                HOOK_FILENAME,
                f"needs UI API {dashboard.requires_ui_api}, but this dashboard has UI API "
                f"{UI_API_VERSION}; update chemunited-workflow",
            )
        self._brand()
        self._manifest["theme_css_url"] = self._file_url(
            dashboard.theme_css, source="theme_css", suffixes=(".css",), what="theme"
        )
        self._pages()
        self._nav()
        self._actions()
        self._widgets()
        if dashboard.protocols is not None:
            self._manifest["protocols"] = {
                "process_categories": dict(dashboard.protocols.process_categories),
                "other_label": dashboard.protocols.other_label,
            }
        return LoadedUi(self._manifest, self._html_pages)

    def _error(self, source: str, message: str) -> None:
        self._manifest["errors"].append(_error(source, message))

    def _file_url(
        self, relative: str | None, *, source: str, suffixes: tuple[str, ...], what: str
    ) -> str | None:
        """The /ui/ext URL of a referenced file, or None (and an error) if it
        has the wrong suffix or doesn't exist."""
        if not relative:
            return None
        posix = PurePosixPath(relative.replace("\\", "/"))
        if posix.suffix.lower() not in suffixes:
            self._error(
                source, f"{what} '{relative}' must be a {' / '.join(suffixes)} file"
            )
            return None
        if resolve_extension_file(self._project_dir, posix.as_posix()) is None:
            self._error(
                source, f"{what} '{relative}' was not found under customizations/ui/"
            )
            return None
        return f"/ui/ext/{posix.as_posix()}"

    def _brand(self) -> None:
        brand = self._dashboard.brand
        if brand is None:
            return
        self._manifest["brand"] = {
            "title": brand.title,
            "subtitle": brand.subtitle,
            "monogram": brand.monogram,
            "logo_url": self._file_url(
                brand.logo, source="brand", suffixes=_IMAGE_SUFFIXES, what="logo"
            ),
        }

    def _page_path_ok(
        self, page: VuePage | HtmlPage, source: str, taken: set[str]
    ) -> bool:
        path = page.path
        if path in BUILTIN_PAGES:
            if not page.replaces:
                self._error(
                    source,
                    f"'{path}' is a built-in page; set replaces=True to replace it",
                )
                return False
        elif page.replaces:
            self._error(source, f"replaces=True, but '{path}' is not a built-in page")
            return False
        elif not _PAGE_PATH.match(path):
            self._error(
                source,
                "a page path is one segment of lowercase letters, digits and hyphens, "
                "like '/sensors'",
            )
            return False
        elif path in _RESERVED_PATHS:
            self._error(source, f"'{path}' is reserved by the server")
            return False
        if path in taken:
            self._error(source, "another page already uses this path")
            return False
        return True

    def _pages(self) -> None:
        taken: set[str] = set()
        for page in self._dashboard.pages:
            source = f"page {page.path}"
            if not self._page_path_ok(page, source, taken):
                continue
            entry: dict[str, Any] = {
                "path": page.path,
                "label": page.label,
                "icon_url": self._file_url(
                    page.icon, source=source, suffixes=_IMAGE_SUFFIXES, what="icon"
                ),
                "after": page.after,
                "hidden": page.hidden,
                "replaces": page.replaces,
            }
            if isinstance(page, VuePage):
                url = self._file_url(
                    page.component, source=source, suffixes=(".vue",), what="component"
                )
                if url is None:
                    continue
                entry.update(kind="vue", component=page.component, component_url=url)
            else:
                entry.update(
                    kind="html",
                    html_url=f"/ui/html{page.path}",
                    refresh_seconds=page.refresh_seconds,
                )
                self._html_pages[page.path] = page
            taken.add(page.path)
            self._manifest["pages"].append(entry)
        known = set(BUILTIN_PAGES) | taken
        for entry in self._manifest["pages"]:
            if entry["after"] is not None and entry["after"] not in known:
                self._error(
                    f"page {entry['path']}",
                    f"after='{entry['after']}' names no page; it goes at the end of the nav",
                )
                entry["after"] = None

    def _nav(self) -> None:
        for item in self._dashboard.nav:
            source = f"nav {item.path}"
            if item.path not in BUILTIN_PAGES:
                self._error(
                    source,
                    "nav entries change built-in pages; set label, icon or hidden on a "
                    "custom page itself",
                )
                continue
            self._manifest["nav"].append(
                {
                    "path": item.path,
                    "label": item.label,
                    "hidden": item.hidden,
                    "order": item.order,
                    "icon_url": self._file_url(
                        item.icon, source=source, suffixes=_IMAGE_SUFFIXES, what="icon"
                    ),
                }
            )

    def _actions(self) -> None:
        if not self._dashboard.actions:
            return
        routes = {
            route["name"]: route for route in discover_custom_routes(self._project_dir)
        }
        for index, action in enumerate(self._dashboard.actions):
            entry = self._action(index, action, routes.get(action.route))
            if entry is not None:
                self._manifest["actions"].append(entry)

    def _action(
        self, index: int, action: PageAction, route: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        source = f"action {action.route} on {action.page}"
        if action.page not in ACTION_PAGES:
            self._error(
                source, f"actions can go on these pages: {', '.join(ACTION_PAGES)}"
            )
            return None
        if route is None:
            self._error(
                source,
                f"no custom route '{action.route}' in customizations/routers/router_hook.py",
            )
            return None
        params = {param["name"]: param for param in route["parameters"]}
        offered = ACTION_PAGES[action.page]
        for param_name, key in action.context.items():
            if param_name not in params:
                self._error(
                    source,
                    f"context names '{param_name}', which {action.route}() doesn't take",
                )
                return None
            if key not in offered:
                self._error(
                    source,
                    f"the {action.page} page offers {', '.join(offered)}, not '{key}'",
                )
                return None
        fields = {f.name: f for f in action.fields}
        for name in fields:
            if name not in params:
                self._error(
                    source, f"field '{name}' is not a parameter of {action.route}()"
                )
                return None
            if name in action.context:
                self._error(
                    source, f"field '{name}' is already filled from the page context"
                )
                return None
        properties: dict[str, Any] = {}
        required: list[str] = []
        for name, param in params.items():
            if name in action.context:
                continue
            field_spec = fields.get(name)
            if field_spec is not None and field_spec.hidden:
                if param["required"]:
                    self._error(source, f"field '{name}' is hidden but has no default")
                    return None
                continue
            properties[name] = _form_property(param, field_spec)
            if param["required"]:
                required.append(name)
        return {
            "id": f"{action.page}:{index}",
            "page": action.page,
            "route": action.route,
            "label": action.label,
            "description": route.get("description"),
            "icon_url": self._file_url(
                action.icon, source=source, suffixes=_IMAGE_SUFFIXES, what="icon"
            ),
            "context": dict(action.context),
            "properties": properties,
            "required": required,
            "remember": [
                f.name for f in action.fields if f.remember and f.name in properties
            ],
            "confirm": action.confirm,
            "refresh": action.refresh,
        }

    def _widgets(self) -> None:
        for widget in self._dashboard.widgets:
            source = f"widget {widget.component}"
            if widget.slot not in SLOTS:
                close = difflib.get_close_matches(widget.slot, SLOTS, n=1)
                hint = (
                    f"did you mean '{close[0]}'?"
                    if close
                    else f"slots are {', '.join(SLOTS)}"
                )
                self._error(source, f"unknown slot '{widget.slot}'; {hint}")
                continue
            url = self._file_url(
                widget.component, source=source, suffixes=(".vue",), what="component"
            )
            if url is None:
                continue
            self._manifest["widgets"].append(
                {
                    "slot": widget.slot,
                    "component": widget.component,
                    "component_url": url,
                    "title": widget.title,
                    "order": widget.order,
                }
            )
