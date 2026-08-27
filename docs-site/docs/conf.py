# Build html
# sphinx-build -b html -v docs docs/_build/html
# start docs/_build/html/index.html

# Configuration file for the Sphinx documentation builder.
import datetime
import shutil
from pathlib import Path

project = 'Chemunited'
YEAR = datetime.date.today().strftime("%Y")
author = "Samuel Saraiva"
copyright = f"{YEAR}, {author}"
release = '0.1.0'

# Add extensions
extensions = [
    'myst_parser',
    'sphinx_copybutton',
    'sphinx_design',
    'sphinxcontrib.video',
    'sphinxcontrib.mermaid',
    'sphinxext.opengraph',
]

# Use Markdown and reStructuredText
source_suffix = {
    '.rst': 'restructuredtext',
    '.md': 'markdown',
}
autodoc_member_order = "bysource"

# Theme
html_theme = 'sphinx_rtd_theme'

# Add custom static files (for custom CSS, logos, etc.)
html_static_path = ['_static']

# Optional: add your logo and favicon
html_logo = "_static/logo.png"
html_favicon = "_static/favicon.ico"

# MyST markdown settings (for more flexible formatting)
myst_enable_extensions = [
    "colon_fence",  # ::: blocks
    "deflist",      # definition lists
    "linkify",      # auto link URLs
    "substitution", # variable placeholders
]

# Render plain ```mermaid fenced code blocks (GitHub-compatible syntax) as diagrams
myst_fence_as_directive = ["mermaid"]

# Enable linking to headings within/across pages via #heading-slug
myst_heading_anchors = 3

# Custom CSS (optional)
html_css_files = [
    'custom.css',
]


def _sync_app_resources(app):
    """Copy icon/component images from the orchestrator app's own resources
    into _static/ before every build, so they never manually drift out of
    sync with what the app actually ships. One-directional and additive
    only: only ever overwrites files that have a same-named counterpart in
    the app's resources, so any future docs-only image with no app
    counterpart stays untouched."""
    repo_root = Path(__file__).resolve().parents[2]
    resources = (
        repo_root
        / "packages/chemunited-orchestrator/src/chemunited/shared/resources"
    )
    static = Path(__file__).resolve().parent / "_static"
    for subdir in ("icons", "components"):
        src_dir = resources / subdir
        dest_dir = static / subdir
        dest_dir.mkdir(parents=True, exist_ok=True)
        for pattern in ("*.svg", "*.ico"):
            for src_file in src_dir.glob(pattern):
                shutil.copyfile(src_file, dest_dir / src_file.name)


def setup(app):
    app.connect("builder-inited", _sync_app_resources)
