"""Dashboard customization for this project: no build step, no Node.

The dashboard reads this file at start-up and applies it in the browser. Edit
it, or the files next to it, and reload the page; problems show on the
dashboard's Customizations page and in `chemunited-workflow ui check`.
Guide: chemunited-workflow's docs/html-ui.md#runtime-customizations.
"""

from chemunited_workflow.ui import Dashboard, VuePage

DASHBOARD = Dashboard(
    # To rebrand and recolour the dashboard, import Brand above and uncomment
    # (theme.css holds the colours):
    # brand=Brand(title="My Lab", subtitle="Protocol Execution Layers", monogram="ML"),
    # theme_css="theme.css",
    pages=[
        VuePage(path="/hello", label="Hello", component="pages/HelloPage.vue"),
    ],
)
