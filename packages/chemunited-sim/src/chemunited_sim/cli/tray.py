"""System tray icon — run the server with Open/Status/Quit tray controls."""

from __future__ import annotations

import ipaddress
import threading
import webbrowser

from fastapi import FastAPI
from loguru import logger

from .server import SimStatus, SimulationState

# ---------------------------------------------------------------------------
# Tray icon helpers
# ---------------------------------------------------------------------------


def _display_host(host: str) -> str:
    try:
        parsed = ipaddress.ip_address(host)
    except ValueError:
        return host
    if parsed.is_unspecified:
        return "127.0.0.1"
    if parsed.version == 6:
        return f"[{host}]"
    return host


def _create_tray_badge_icon(size: int = 64):
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    center = size / 2
    outer_margin = max(1, size * 0.04)
    white_margin = size * 0.18
    accent_margin = size * 0.24

    draw.ellipse(
        (outer_margin, outer_margin, size - outer_margin - 1, size - outer_margin - 1),
        fill=(40, 47, 56, 255),
    )
    draw.ellipse(
        (white_margin, white_margin, size - white_margin - 1, size - white_margin - 1),
        fill=(255, 255, 255, 255),
    )
    draw.ellipse(
        (
            accent_margin,
            accent_margin,
            size - accent_margin - 1,
            size - accent_margin - 1,
        ),
        fill=(46, 160, 67, 255),
    )

    point_radius = max(1.5, size * 0.075)
    point_offset = size * 0.31
    for x, y in (
        (center, center - point_offset),
        (center + point_offset, center),
        (center, center + point_offset),
        (center - point_offset, center),
    ):
        draw.ellipse(
            (x - point_radius, y - point_radius, x + point_radius, y + point_radius),
            fill=(255, 255, 255, 255),
        )
    return image


# ---------------------------------------------------------------------------
# Simulation shutdown
# ---------------------------------------------------------------------------


def _stop_running_simulation(state: SimulationState) -> None:
    """Gracefully stop an in-flight simulation, mirroring POST /simulation/stop."""
    if state.sim_status != SimStatus.RUNNING:
        return
    logger.info("Tray quit — stopping in-flight simulation before shutdown")
    state._stop_event.set()
    if state._worker_thread is not None:
        state._worker_thread.join(timeout=5.0)
    state.sim_status = SimStatus.IDLE


# ---------------------------------------------------------------------------
# Tray runner
# ---------------------------------------------------------------------------


def run_with_tray(app: FastAPI, host: str, port: int, state: SimulationState) -> None:
    """Run uvicorn in a background thread with a system tray icon.

    The tray menu offers Open API Docs / Status / Quit — Quit gracefully stops
    any running simulation, then shuts uvicorn down.
    """
    try:
        import pystray
    except ImportError as exc:
        raise RuntimeError(
            "--tray requires pystray and pillow. "
            "Install with: pip install chemunited-sim[tray]"
        ) from exc

    import uvicorn

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        access_log=False,
        log_config=None,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="chemunited-fastapi", daemon=True)
    thread.start()

    app_url = f"http://{_display_host(host)}:{port}/"

    def _open_app(icon, item):
        webbrowser.open(app_url)

    def _show_status(icon, item):
        icon.notify(f"Status: {state.sim_status.value}", "chemunited-sim")

    def _quit_app(icon, item):
        _stop_running_simulation(state)
        server.should_exit = True
        if thread.is_alive():
            thread.join(timeout=5.0)
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("Open API Docs", _open_app),
        pystray.MenuItem("Status", _show_status),
        pystray.MenuItem("Quit", _quit_app),
    )
    icon = pystray.Icon(
        "chemunited-sim",
        _create_tray_badge_icon(),
        "chemunited-sim",
        menu,
    )

    def _setup(icon_obj):
        icon_obj.visible = True

    try:
        icon.run(setup=_setup)
    finally:
        _stop_running_simulation(state)
        server.should_exit = True
