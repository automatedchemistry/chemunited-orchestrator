"""Capture screenshots of the live ChemUnited browser dashboard for the docs.

Prerequisites:
    .venv\\Scripts\\python.exe -m pip install playwright
    .venv\\Scripts\\python.exe -m playwright install chromium

The dashboard must already be running with a project loaded (e.g. via the
Dashboard Launcher) before running this script, otherwise pages render
empty-state screenshots.

Usage (run with cwd = docs/, so output paths match this repo's convention):
    .venv\\Scripts\\python.exe dashboard_screenshots.py [--base-url http://127.0.0.1:3116]
"""

from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright

PAGES = {
    "dashboard_overview.png": "/",
    "dashboard_run_control.png": "/run-control",
    "dashboard_protocols.png": "/protocols",
    "dashboard_monitoring.png": "/monitoring",
    "dashboard_logs.png": "/logs",
    "dashboard_devices.png": "/devices",
}


def capture(base_url: str, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        for filename, route in PAGES.items():
            url = base_url.rstrip("/") + route
            page.goto(url, wait_until="networkidle")
            page.wait_for_timeout(500)  # let Vue finish rendering after the last request
            out_path = out_dir / filename
            page.screenshot(path=str(out_path), full_page=True)
            print(f"Saved {out_path} <- {url}")
        browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:3116",
        help="Base URL of the running dashboard (default: %(default)s)",
    )
    args = parser.parse_args()
    capture(args.base_url, Path("_static"))
