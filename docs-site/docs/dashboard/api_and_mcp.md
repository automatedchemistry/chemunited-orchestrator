# API & MCP Tools

Everything the [dashboard](overview.md) does is backed by a REST API, and the same functionality is also available
as MCP tools for LLM-agent-driven automation. Both are served by the same [work-server](overview.md) process.

## REST API

The work-server exposes interactive API documentation (Swagger UI) at `/docs` on whatever host/port it is running
on — this is the live source of truth for exact request/response schemas, so it is not duplicated here. The
endpoint groups available are:

| Group | Covers |
|---|---|
| Project | Load/inspect the currently open project. |
| Processes | List processes, inspect a process's parameter schema and source code. |
| Protocols | List, create, retrieve, and delete saved protocol script files. |
| Run control | Start/cancel a run, check status, fetch the run report, and stream live run events (Server-Sent Events). |
| Logs | List, search, tail, and archive log files. |
| Components | List associated components and ping them for connectivity. |
| Monitoring | Start/stop standalone sensor-polling sessions and read back their time-series data, independent of any protocol run. |

## MCP tools

When the work-server is started with `--with-mcp`, it exposes the same capabilities as MCP tools on the same port,
for use by an MCP-compatible LLM client or agent.

| Group | Tools |
|---|---|
| Project | `load_project`, `get_project` |
| Processes | `list_processes`, `get_process_schema`, `read_process` |
| Protocols | `list_protocols`, `get_protocol`, `create_protocol`, `delete_protocol` |
| Run control | `start_run`, `get_active_run`, `get_run_status`, `get_run_report`, `cancel_run`, `drain_run_pool` |
| Components | `get_components`, `ping_components`, `ping_component` |
| Monitoring & Logs | Standalone monitoring session management and log search/read tools, mirroring the REST Monitoring/Logs groups above. |

<div class="info-block">
<strong>💡 Note</strong><br>
This is a separate MCP server from the orchestrator's own Project MCP server (see
<a href="../developer/backend.md">Working with Backend</a>), which exposes local project <em>files</em> for editing
while the desktop app has a project open. This work-server MCP exposes <em>run control</em> — starting, stopping,
and inspecting protocol executions.
</div>

<div class="warning-block">
<strong>⚠️ Warning</strong><br>
Like the REST API, the MCP interface has no built-in authentication. Only enable <code>--with-mcp</code> on trusted
networks, and be aware that any connected MCP client can start or cancel runs on real hardware.
</div>