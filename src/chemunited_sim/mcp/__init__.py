"""chemunited_sim.mcp — MCP server factory."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .tools import register_tools


def create_mcp_server(
    *,
    host: str = "127.0.0.1",
    port: int = 1472,
    streamable_http_path: str = "/mcp",
) -> FastMCP:
    """Create and return a configured MCP server for chemunited-sim.

    Tools read and mutate the same module-level simulation state the REST
    API uses (``chemunited_sim.cli.server.get_state()``), so loading a
    project or starting a run via MCP is immediately visible to the REST API
    and vice versa.
    """
    mcp = FastMCP(
        "chemunited-sim",
        host=host,
        port=port,
        streamable_http_path=streamable_http_path,
    )
    register_tools(mcp)
    return mcp
