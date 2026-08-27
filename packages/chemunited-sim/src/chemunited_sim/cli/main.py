"""CLI entry point — parse arguments, initialise state, launch uvicorn."""

from __future__ import annotations

import argparse
import queue
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from ..worker.config import SimConfig
from . import server as _server_module
from .clock import SimClock
from .server import SimStatus, SimulationState, _do_load_project, app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chemunited-sim",
        description="Start the chemunited simulation server.",
    )
    parser.add_argument(
        "project",
        nargs="?",
        type=Path,
        default=None,
        help="Path to a project folder or .chemunited ZIP. "
        "If omitted the server starts in NO_PROJECT state.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=1472,
        help="Port for the FastAPI server (default: 1472).",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("./simulations/"),
        metavar="PATH",
        help="Directory where .db files are saved (default: ./simulations/).",
    )
    parser.add_argument(
        "--tray",
        action="store_true",
        help="Run with a system tray icon; use its Quit item to stop the "
        "server (default: blocking terminal mode, Ctrl+C to stop).",
    )
    parser.add_argument(
        "--with-mcp",
        action="store_true",
        help="Mount an MCP (Model Context Protocol) streamable-HTTP endpoint "
        "at /mcp on the same host/port, so an LLM agent can drive the "
        "server directly. See docs/mcp-tools.md.",
    )
    return parser


def _mount_mcp(app: FastAPI, *, host: str, port: int) -> None:
    """Mount the MCP server onto *app* at ``/mcp`` and wire its session
    manager into the app's lifespan.

    Must be called before the app is handed to uvicorn (directly or via
    ``run_with_tray``) — the session manager only starts/stops around the
    ASGI lifespan.
    """
    from ..mcp import create_mcp_server

    mcp_server = create_mcp_server(host=host, port=port, streamable_http_path="/")
    mcp_sub_app = mcp_server.streamable_http_app()
    app.mount("/mcp", mcp_sub_app)

    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def _lifespan_with_mcp(app: FastAPI):
        async with mcp_server.session_manager.run():
            async with original_lifespan(app):
                yield

    app.router.lifespan_context = _lifespan_with_mcp


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    db_dir = args.db.resolve()
    clock = SimClock()
    cmd_queue: queue.Queue = queue.Queue()

    state = SimulationState(
        sim_status=SimStatus.NO_PROJECT,
        current_t=0.0,
        config=SimConfig(),
        db_path=None,
        project=None,
        clock=clock,
        cmd_queue=cmd_queue,
        db_dir=db_dir,
    )
    _server_module._state = state

    if args.project is not None:
        _do_load_project(args.project.resolve(), state)

    if args.with_mcp:
        _mount_mcp(app, host="127.0.0.1", port=args.port)

    if args.tray:
        from .tray import run_with_tray

        try:
            run_with_tray(app, host="127.0.0.1", port=args.port, state=state)
        except RuntimeError as exc:
            parser.error(str(exc))
    else:
        uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
