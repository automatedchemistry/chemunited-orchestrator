"""Example dashboard customization for this project.

The dashboard reads this file at start-up (GET /ui/manifest) and applies it in
the browser: nothing is built, and no Node or npm is needed. Edit it or the
files next to it, then reload the page. Problems show on the dashboard's
Customizations page. See docs/html-ui.md#runtime-customizations.
"""

from __future__ import annotations

import html
from pathlib import Path

from chemunited_workflow.ui import (
    ActionField,
    Dashboard,
    HtmlPage,
    PageAction,
    VuePage,
    Widget,
)

PROJECT_DIR = Path(__file__).resolve().parents[2]


def protocol_history() -> str:
    """The saved protocol runs as a plain HTML table, rendered by Python."""
    runs = sorted((PROJECT_DIR / "protocols_historic").glob("*.json"))
    rows = "".join(
        f"<tr><td>{html.escape(run.stem)}</td><td>{run.stat().st_size:,} B</td></tr>"
        for run in runs
    )
    return (
        "<style>body{font-family:system-ui,sans-serif;margin:1.5rem;color:#334e68}"
        "table{border-collapse:collapse;width:100%}"
        "td,th{padding:.45rem .6rem;border-bottom:1px solid #d8e4ee;text-align:left}</style>"
        f"<table><tr><th>Protocol run</th><th>Size</th></tr>{rows}</table>"
    )


DASHBOARD = Dashboard(
    # To rebrand and recolour the dashboard, import Brand above and uncomment
    # these two lines (theme.css holds the colours):
    # brand=Brand(title="Flow Synthesis Lab", subtitle="Example project", monogram="FSL"),
    # theme_css="theme.css",
    pages=[
        VuePage(
            path="/reactor",
            label="Reactor",
            component="pages/ReactorPage.vue",
            icon="assets/flask.svg",
            after="/monitoring",
        ),
        HtmlPage(
            path="/history", label="History", render=protocol_history, after="/logs"
        ),
    ],
    actions=[
        # A button on the Dashboard; its two number fields come from the
        # type hints of residence_time_min() in routers/router_hook.py.
        PageAction(
            page="dashboard",
            route="residence_time_min",
            label="Residence time",
            fields=[
                ActionField("flow_rate_ml_min", label="Flow (mL/min)"),
                ActionField("reactor_volume_ml", label="Volume (mL)"),
            ],
        ),
        # A button on Export that gets the selected runs as `logs`.
        PageAction(
            page="export",
            route="summarize_runs",
            label="Summarize",
            context={"logs": "selection"},
            fields=[ActionField("note", placeholder="optional note", remember=True)],
        ),
    ],
    widgets=[
        Widget(
            slot="dashboard.cards",
            component="widgets/RunCard.vue",
            title="Example widget",
        )
    ],
)
