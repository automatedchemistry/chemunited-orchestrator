"""What a project's ``customizations/ui/ui_hook.py`` can declare.

A project customizes the bundled dashboard by exporting
``DASHBOARD = Dashboard(...)`` from ``{project_dir}/customizations/ui/ui_hook.py``.
The server checks it and serves it as JSON at ``GET /ui/manifest``; the
dashboard applies it in the browser, so customizing needs no build step.
File paths (components, icons, the theme) are relative to
``customizations/ui/``. See docs/html-ui.md#runtime-customizations.
"""

from __future__ import annotations

from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field

UI_API_VERSION = 1

# Page paths the bundled dashboard serves; a VuePage/HtmlPage may only take
# one over with replaces=True.
BUILTIN_PAGES: dict[str, str] = {
    "/": "Dashboard",
    "/run-control": "Run Control",
    "/protocols": "Protocols",
    "/monitoring": "Monitoring",
    "/devices": "Devices",
    "/logs": "Logs",
    "/export": "Export",
}

# Where a Widget can go, and the context each slot hands its widgets.
SLOTS: dict[str, str] = {
    "dashboard.cards": "Cards below the Dashboard's summary cards. "
    "Context: project_dir, run_id, run_state.",
    "device.panel": "Inside the device panel opened from the Dashboard's platform "
    "picture. Context: device (id, label, figure).",
    "run-control.panels": "Panels below Run Control's controls. Context: run_id, run_state.",
    "devices.panels": "Panels below the Devices connectivity map. Context: components.",
}

# Pages that show PageActions, and the context values each can pass to a route.
ACTION_PAGES: dict[str, tuple[str, ...]] = {
    "dashboard": ("project_dir",),
    "run-control": ("run_id", "run_state"),
    "devices": ("components",),
    "export": ("selection",),
}


class _Spec(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Brand(_Spec):
    """The sidebar's brand block. ``logo`` wins over ``monogram``."""

    title: str | None = None
    subtitle: str | None = None
    monogram: str | None = Field(default=None, max_length=4)
    logo: str | None = None


class NavItem(_Spec):
    """Change a built-in nav entry: rename, hide, move (``order``) or re-icon it.

    Built-in entries have orders 10, 20, ... 70 in their usual sequence.
    """

    path: str
    label: str | None = None
    hidden: bool = False
    order: int | None = None
    icon: str | None = None


class _Page(_Spec):
    path: str
    label: str
    icon: str | None = None
    # Nav entry to place this page after; the end of the nav when unset.
    after: str | None = None
    # Reachable by URL but left out of the nav.
    hidden: bool = False
    # Take over a built-in page's path (and its nav entry).
    replaces: bool = False


class VuePage(_Page):
    """A page written as a ``.vue`` file; the browser compiles it."""

    component: str


class HtmlPage(_Page):
    """A page whose HTML comes from a Python function, shown in a sandboxed iframe."""

    render: Callable[[], str]
    refresh_seconds: float | None = Field(default=None, gt=0)


class Widget(_Spec):
    """A ``.vue`` component placed in one of the built-in pages' slots (``SLOTS``)."""

    slot: str
    component: str
    title: str | None = None
    order: int = 0


class ActionField(_Spec):
    """How one route parameter shows in a PageAction's form.

    Parameters without an ActionField still get a field; their type comes
    from the route function's type hints.
    """

    name: str
    label: str | None = None
    placeholder: str | None = None
    # Keep the last value entered, per browser.
    remember: bool = False
    # Leave the field out and let the parameter take its default.
    hidden: bool = False

    def __init__(self, name: str | None = None, /, **data: Any) -> None:
        if name is not None:
            data["name"] = name
        super().__init__(**data)


class PageAction(_Spec):
    """A button on a built-in page that calls a custom route (``CUSTOM_ROUTES``).

    ``context`` maps route parameters to values the page provides (see
    ``ACTION_PAGES``); the remaining parameters become form fields.
    """

    page: str
    route: str
    label: str
    icon: str | None = None
    context: dict[str, str] = Field(default_factory=dict)
    fields: list[ActionField] = Field(default_factory=list)
    # Ask before calling the route.
    confirm: str | None = None
    # Reload the page's data once the route succeeds.
    refresh: bool = False


class ProtocolsPage(_Spec):
    """Protocols page settings. ``process_categories`` maps a process-name
    prefix to a tab label; processes matching no prefix go under ``other_label``."""

    process_categories: dict[str, str] = Field(default_factory=dict)
    other_label: str = "Other"


class Dashboard(_Spec):
    """Everything a project changes about the dashboard."""

    requires_ui_api: int = UI_API_VERSION
    brand: Brand | None = None
    theme_css: str | None = None
    pages: list[VuePage | HtmlPage] = Field(default_factory=list)
    nav: list[NavItem] = Field(default_factory=list)
    actions: list[PageAction] = Field(default_factory=list)
    widgets: list[Widget] = Field(default_factory=list)
    protocols: ProtocolsPage | None = None
