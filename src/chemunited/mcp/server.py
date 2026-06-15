from __future__ import annotations

import socket
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from chemunited.mcp.project_files import ProjectFileAccess
from chemunited.mcp.qt_bridge import QtMainThreadBridge
from chemunited.project.platform_svg import (
    PLATFORM_SVG_RELATIVE_PATH,
    export_platform_svg,
)
from chemunited.shared.enums import WindowCategory

if TYPE_CHECKING:
    from chemunited.setup import SetupWindow

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
MAX_PORT = 8799
MCP_PATH = "/mcp"

_MCP_INSTRUCTIONS = (Path(__file__).parent / "instructions.md").read_text(
    encoding="utf-8"
)


@dataclass(slots=True)
class McpServiceResult:
    ok: bool
    message: str
    url: str | None = None


class ProjectMcpService:
    def __init__(self, window: SetupWindow):
        self._window = window
        self._bridge = QtMainThreadBridge(window)
        self._files = ProjectFileAccess(self._current_working_dir)
        self._server: Any | None = None
        self._thread: threading.Thread | None = None
        self.url: str | None = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> McpServiceResult:
        if self.is_running:
            return McpServiceResult(True, "Project MCP is already running.", self.url)
        if self._current_working_dir() is None:
            return McpServiceResult(
                False,
                "Load or create a project before enabling MCP.",
            )

        try:
            import uvicorn
            from mcp.server.fastmcp import FastMCP
        except Exception:
            return McpServiceResult(
                False,
                "Project MCP requires the 'mcp' package. "
                "Reinstall the environment from pyproject.toml.",
            )

        port = self._first_available_port()
        if port is None:
            return McpServiceResult(
                False,
                f"No available localhost port in {DEFAULT_PORT}-{MAX_PORT}.",
            )

        mcp = FastMCP(
            "ChemUnited Project",
            stateless_http=True,
            json_response=True,
            instructions=_MCP_INSTRUCTIONS,
        )
        self._register_tools(mcp)

        config = uvicorn.Config(
            mcp.streamable_http_app(),
            host=DEFAULT_HOST,
            port=port,
            log_level="warning",
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(
            target=self._server.run,
            name="chemunited-project-mcp",
            daemon=True,
        )
        self._thread.start()
        self.url = f"http://{DEFAULT_HOST}:{port}{MCP_PATH}"
        logger.bind(window=WindowCategory.SETUP).success(
            f"Project MCP running at {self.url}"
        )
        return McpServiceResult(True, "Project MCP started.", self.url)

    def stop(self) -> McpServiceResult:
        if not self.is_running:
            self._server = None
            self._thread = None
            self.url = None
            return McpServiceResult(True, "Project MCP is not running.")

        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=3)
        self._server = None
        self._thread = None
        old_url = self.url
        self.url = None
        logger.bind(window=WindowCategory.SETUP).info("Project MCP stopped.")
        return McpServiceResult(True, "Project MCP stopped.", old_url)

    def refresh_project_from_mcp(self) -> dict[str, Any]:
        def refresh() -> dict[str, Any]:
            orchestrator = self._window.orchestrator
            reason = orchestrator.refresh_project_block_reason()
            if reason is not None:
                return {"ok": False, "blocked": True, "message": reason}

            ok = orchestrator.refresh_current_project()
            if ok:
                orchestrator._sync_project_views_after_refresh()
            self._window.update_project_actions()
            return {
                "ok": ok,
                "blocked": False,
                "message": "Project refreshed." if ok else "Project refresh failed.",
            }

        try:
            return self._bridge.call(refresh, timeout=60)
        except Exception as exc:
            logger.bind(window=WindowCategory.SETUP).opt(exception=exc).error(
                f"Project MCP refresh failed: {exc}"
            )
            return {"ok": False, "blocked": False, "message": str(exc)}

    def export_platform_svg_from_mcp(self, *, scale: float = 2.0) -> dict[str, Any]:
        def export() -> dict[str, Any]:
            working_dir = self._current_working_dir()
            if working_dir is None:
                raise RuntimeError("No project is currently open.")

            path = working_dir / PLATFORM_SVG_RELATIVE_PATH
            export_platform_svg(self._window.scene_attribute, path, scale=scale)
            return {
                "path": PLATFORM_SVG_RELATIVE_PATH.as_posix(),
                "bytes": path.stat().st_size,
                "scale": scale,
                "message": "Platform SVG exported.",
            }

        try:
            payload = self._bridge.call(export, timeout=60)
        except Exception as exc:
            logger.bind(window=WindowCategory.SETUP).opt(exception=exc).error(
                f"Project MCP platform SVG export failed: {exc}"
            )
            return {"ok": False, "message": str(exc)}
        return {"ok": True, **payload}

    def _register_tools(self, mcp: Any) -> None:
        @mcp.tool()
        def list_project_files() -> dict[str, Any]:
            """List the current project's MCP-exposed files."""
            return self._handle_file_call(lambda: {"files": self._files.list_files()})

        @mcp.tool()
        def read_project_file(path: str) -> dict[str, Any]:
            """Read an MCP-exposed project file as UTF-8 text."""
            return self._handle_file_call(
                lambda: {"path": path, "content": self._files.read_file(path)}
            )

        @mcp.tool()
        def write_project_file(path: str, content: str) -> dict[str, Any]:
            """Overwrite or create an MCP-exposed project text file."""
            return self._handle_file_call(lambda: self._files.write_file(path, content))

        @mcp.tool()
        def delete_project_file(path: str) -> dict[str, Any]:
            """Delete a normal protocols/*.py file from the current project."""
            return self._handle_file_call(lambda: self._files.delete_file(path))

        @mcp.tool()
        def refresh_project() -> dict[str, Any]:
            """Reload the live Setup window from the current project files."""
            return self.refresh_project_from_mcp()

        @mcp.tool()
        def export_platform_svg(scale: float = 2.0) -> dict[str, Any]:
            """Export the live platform canvas to draw/platform.svg."""
            return self.export_platform_svg_from_mcp(scale=scale)

    def _handle_file_call(self, call) -> dict[str, Any]:
        try:
            payload = call()
        except Exception as exc:
            return {"ok": False, "message": str(exc)}
        return {"ok": True, **payload}

    def _current_working_dir(self) -> Path | None:
        working_dir = getattr(self._window.orchestrator, "working_dir", None)
        return Path(working_dir) if working_dir is not None else None

    @staticmethod
    def _first_available_port() -> int | None:
        for port in range(DEFAULT_PORT, MAX_PORT + 1):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    sock.bind((DEFAULT_HOST, port))
                except OSError:
                    continue
                return port
        return None
