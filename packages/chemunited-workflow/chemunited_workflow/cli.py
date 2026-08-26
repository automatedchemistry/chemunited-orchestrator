from __future__ import annotations

import base64
import ipaddress
import os
import re
import subprocess  # nosec B404
import sys
import threading
import webbrowser
from io import BytesIO
from pathlib import Path

import click

from chemunited_workflow.project_loader import (
    ProjectLoadError,
    format_broken_project_error,
    load_project,
)

_DEFAULT_ICON_PATH = Path(__file__).parent / "chemunited.svg"


# ---------------------------------------------------------------------------
# Tray icon helpers
# ---------------------------------------------------------------------------


def _square_icon(image, size: int = 64):
    from PIL import Image, ImageOps

    image = ImageOps.contain(image.convert("RGBA"), (size, size))
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    offset = ((size - image.width) // 2, (size - image.height) // 2)
    canvas.paste(image, offset, image)
    return canvas


def _load_embedded_png_icon(svg_path: Path, size: int = 64):
    from PIL import Image

    text = svg_path.read_text(encoding="utf-8")
    match = re.search(r"data:image/png;base64,([^\"']+)", text, re.DOTALL)
    if not match:
        raise ValueError(f"No embedded PNG found in {svg_path}")
    png_bytes = base64.b64decode("".join(match.group(1).split()))
    with Image.open(BytesIO(png_bytes)) as image:
        return _square_icon(image, size=size)


def _create_tray_badge_icon(size: int = 64):
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    center = size / 2
    outer_margin = max(1, size * 0.04)
    white_margin = size * 0.18
    blue_margin = size * 0.24

    draw.ellipse(
        (outer_margin, outer_margin, size - outer_margin - 1, size - outer_margin - 1),
        fill=(40, 47, 56, 255),
    )
    draw.ellipse(
        (white_margin, white_margin, size - white_margin - 1, size - white_margin - 1),
        fill=(255, 255, 255, 255),
    )
    draw.ellipse(
        (blue_margin, blue_margin, size - blue_margin - 1, size - blue_margin - 1),
        fill=(30, 144, 255, 255),
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


def _load_tray_icon(size: int = 64):
    try:
        return _load_embedded_png_icon(_DEFAULT_ICON_PATH, size=size)
    except Exception:
        return _create_tray_badge_icon(size=size)


def _pythonw_executable() -> Path | None:
    """Return pythonw.exe next to the current interpreter, or None."""
    executable = Path(sys.executable)
    if executable.stem.lower() == "pythonw":
        return None  # already windowless
    candidate = executable.with_name("pythonw.exe")
    return candidate if candidate.exists() else None


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


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx: click.Context) -> None:
    """Conditional DAG workflow engine for chemistry lab automation.

    Executes protocol graphs where each node calls a device HTTP endpoint and
    the result routes execution through the graph (branches, loopbacks, parallel
    steps).

    \b
    Quick start:
      chemunited-workflow serve my_project/

    Run without a subcommand to start the FastAPI server with default settings
    (equivalent to 'serve').
    """
    if ctx.invoked_subcommand is None:
        ctx.invoke(serve)


@main.command("serve")
@click.argument(
    "project_dir",
    required=False,
    default=None,
    type=click.Path(exists=True, file_okay=False, resolve_path=True, path_type=Path),
)
@click.option(
    "--host",
    default="127.0.0.1",
    show_default=True,
    help="Bind host for the server.",
)
@click.option(
    "--port",
    default=None,
    type=int,
    help="Bind port. Defaults to 3116.",
)
@click.option(
    "--reload",
    is_flag=True,
    default=False,
    help="Enable auto-reload (development only, FastAPI only, incompatible with --tray).",
)
@click.option(
    "--advertise",
    is_flag=True,
    default=False,
    help=(
        "Advertise the dashboard on the LAN via mDNS so other machines can discover it "
        "(requires pip install chemunited-workflow[discovery]). "
        "Implies --host 0.0.0.0 when the default host is used."
    ),
)
@click.option(
    "--advertise-name",
    "advertise_name",
    default=None,
    metavar="NAME",
    help="Name shown in mDNS discovery. Defaults to 'ChemUnited @ <hostname>'.",
)
@click.option(
    "--with-mcp",
    "with_mcp",
    is_flag=True,
    default=False,
    help="Also expose an MCP streamable-HTTP endpoint within the FastAPI server.",
)
@click.option(
    "--tray",
    "use_tray",
    is_flag=True,
    default=False,
    help="Run in the Windows system tray (uvicorn in background thread, tray icon on main thread).",
)
@click.option(
    "--silent",
    is_flag=True,
    default=False,
    help="Detach from the terminal so no console window stays open (--tray only, Windows only).",
)
def serve(
    project_dir: Path | None,
    host: str,
    port: int | None,
    reload: bool,
    advertise: bool,
    advertise_name: str | None,
    with_mcp: bool,
    use_tray: bool,
    silent: bool,
) -> None:
    """Start the FastAPI server (browser dashboard + REST API).

    PROJECT_DIR pre-loads a project at startup. Without it the server starts
    empty; load a project later via PUT /project or the load_project MCP tool.

    \b
    Start the server:
      chemunited-workflow serve my_project/
      chemunited-workflow serve my_project/ --port 8080
      chemunited-workflow serve --reload          # dev mode, no project
      Dashboard:   http://127.0.0.1:3116/
      Swagger UI:  http://127.0.0.1:3116/docs

    \b
    With MCP streamable-HTTP endpoint on the same port:
      chemunited-workflow serve my_project/ --with-mcp
      Dashboard:  http://127.0.0.1:3116/
      MCP:        http://127.0.0.1:3116/mcp

    \b
    LAN advertisement -- expose the dashboard to other machines on the network:
      chemunited-workflow serve my_project/ --advertise
      chemunited-workflow serve my_project/ --advertise --advertise-name "Flow Synthesis Lab"
      Requires:  pip install chemunited-workflow[discovery]
      Binds to 0.0.0.0 and registers an mDNS record so other devices can
      discover the dashboard at http://<hostname>.local:3116/ without knowing
      the server's IP address. The record is withdrawn cleanly on exit.

    \b
    System tray mode -- run minimised to the Windows tray:
      chemunited-workflow serve my_project/ --tray
      chemunited-workflow serve my_project/ --tray --silent   # no terminal window
      Incompatible with --reload.

    \b
    Full combination:
      chemunited-workflow serve my_project/ --advertise --advertise-name "Flow Synthesis Lab" --with-mcp --tray --silent
    """
    # --- FastAPI mode -------------------------------------------------------
    try:
        import uvicorn
    except ImportError:
        raise click.UsageError(
            "uvicorn is not installed. Install the [server] extra:\n"
            "  pip install chemunited-workflow[server]"
        )

    if use_tray and reload:
        raise click.UsageError("--reload is incompatible with --tray.")

    if silent and not use_tray:
        raise click.UsageError("--silent requires --tray.")

    if silent:
        pythonw = _pythonw_executable()
        if pythonw is not None:
            args = [a for a in sys.argv[1:] if a != "--silent"]
            subprocess.Popen(  # nosec B603
                [str(pythonw), "-m", "chemunited_workflow.cli", *args],
                close_fds=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=(
                    getattr(subprocess, "DETACHED_PROCESS", 0)
                    | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                ),
            )
            return

    if Path(sys.executable).stem.lower() == "pythonw":
        _log_path = Path.home() / ".chemunited-workflow" / "server.log"
        _log_path.parent.mkdir(exist_ok=True)
        sys.stderr = open(_log_path, "a", encoding="utf-8")  # noqa: WPS515
        sys.stdout = open(os.devnull, "w")

    from chemunited_workflow.api import create_api
    from chemunited_workflow.api.dependencies import get_project_holder

    resolved_port = port if port is not None else 3116

    if advertise and host == "127.0.0.1":
        host = "0.0.0.0"  # nosec B104

    app = create_api(
        with_mcp=with_mcp,
        host=host,
        port=resolved_port,
    )

    if project_dir is not None:
        try:
            modules = load_project(project_dir)
        except ProjectLoadError as exc:
            raise click.BadParameter(str(exc), param_hint="project_dir") from exc
        try:
            app.dependency_overrides[get_project_holder]().load(modules)
        except Exception as exc:
            raise click.BadParameter(
                format_broken_project_error(
                    exc,
                    project_dir,
                    f"Failed to initialize services for project '{project_dir}'",
                ),
                param_hint="project_dir",
            ) from exc

    zc = None
    zc_info = None
    if advertise:
        try:
            from zeroconf import ServiceInfo, Zeroconf
        except ImportError:
            raise click.UsageError(
                "--advertise requires the [discovery] extra:\n"
                "  pip install chemunited-workflow[discovery]"
            )
        import socket

        _s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            _s.connect(("8.8.8.8", 80))
            lan_ip = _s.getsockname()[0]
        finally:
            _s.close()

        hostname = socket.gethostname()
        display_name = advertise_name or f"ChemUnited @ {hostname}"
        mdns_host = advertise_name.replace(" ", "-") if advertise_name else hostname
        service_name = f"{display_name}._http._tcp.local."
        zc_info = ServiceInfo(
            "_http._tcp.local.",
            service_name,
            addresses=[socket.inet_aton(lan_ip)],
            port=resolved_port,
            properties={"path": "/"},
            server=f"{mdns_host}.local.",
        )
        zc = Zeroconf()
        zc.register_service(zc_info)
        click.echo(
            f"mDNS: advertising '{display_name}' -> "
            f"http://{lan_ip}:{resolved_port}/ | "
            f"http://{mdns_host}.local:{resolved_port}/"
        )

    if use_tray:
        try:
            import pystray
        except ImportError:
            raise click.UsageError(
                "--tray requires pystray and pillow:\n"
                "  pip install chemunited-workflow[tray]"
            )

        config = uvicorn.Config(
            app,
            host=host,
            port=resolved_port,
            access_log=False,
            log_config=None,
            log_level="warning",
        )
        server = uvicorn.Server(config)
        thread = threading.Thread(
            target=server.run, name="chemunited-fastapi", daemon=True
        )
        thread.start()

        app_url = f"http://{_display_host(host)}:{resolved_port}/"

        def _open_app(icon, item):
            webbrowser.open(app_url)

        def _show_status(icon, item):
            icon.notify("FastAPI app is running", "chemunited-workflow")

        def _quit_app(icon, item):
            server.should_exit = True
            if thread.is_alive():
                thread.join(timeout=5.0)
            icon.stop()

        menu = pystray.Menu(
            pystray.MenuItem("Open App", _open_app),
            pystray.MenuItem("Status", _show_status),
            pystray.MenuItem("Quit", _quit_app),
        )
        icon = pystray.Icon(
            "chemunited-workflow",
            _load_tray_icon(),
            "chemunited-workflow",
            menu,
        )

        def _setup(icon_obj):
            icon_obj.visible = True

        try:
            icon.run(setup=_setup)
        finally:
            server.should_exit = True
            if zc is not None:
                zc.unregister_service(zc_info)
                zc.close()
    else:
        try:
            uvicorn.run(app, host=host, port=resolved_port, reload=reload)
        finally:
            if zc is not None:
                zc.unregister_service(zc_info)
                zc.close()


if __name__ == "__main__":
    main()
