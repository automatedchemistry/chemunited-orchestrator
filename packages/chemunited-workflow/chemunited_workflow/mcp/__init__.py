"""chemunited_workflow.mcp — MCP server factory."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from chemunited_workflow.api.project_holder import ProjectHolder

from .tools import register_tools


def create_mcp_server(
    *,
    host: str = "127.0.0.1",
    port: int = 3117,
    streamable_http_path: str = "/mcp",
    holder: ProjectHolder | None = None,
) -> FastMCP:
    """Create and return a configured MCP server.

    The server starts with no project loaded. Use the ``load_project`` tool to
    load a project at runtime. The server supports switching projects via
    ``load_project`` as long as no run is active.

    Pass an existing ``holder`` to share project state with another server
    (e.g. when mounting the MCP endpoint inside a FastAPI app).
    """
    if holder is None:
        holder = ProjectHolder()
    mcp = FastMCP(
        "chemunited",
        host=host,
        port=port,
        streamable_http_path=streamable_http_path,
    )
    register_tools(mcp, holder)
    return mcp
