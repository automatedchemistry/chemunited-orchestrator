"""Dashboard customization for ``customizations/ui/ui_hook.py``.

Example::

    from chemunited_workflow.ui import Brand, Dashboard, VuePage

    DASHBOARD = Dashboard(
        brand=Brand(title="Flow Lab", monogram="FL"),
        pages=[VuePage(path="/sensors", label="Sensors", component="pages/Sensors.vue")],
    )
"""

from .models import (
    ACTION_PAGES,
    BUILTIN_PAGES,
    SLOTS,
    UI_API_VERSION,
    ActionField,
    Brand,
    Dashboard,
    HtmlPage,
    NavItem,
    PageAction,
    ProtocolsPage,
    VuePage,
    Widget,
)

__all__ = [
    "ACTION_PAGES",
    "BUILTIN_PAGES",
    "SLOTS",
    "UI_API_VERSION",
    "ActionField",
    "Brand",
    "Dashboard",
    "HtmlPage",
    "NavItem",
    "PageAction",
    "ProtocolsPage",
    "VuePage",
    "Widget",
]
