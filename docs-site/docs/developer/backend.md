# Working with Backend

Everything the GUI does is backed by plain files and local HTTP servers. Advanced users can script against these
directly — including through MCP, so an LLM agent can inspect or drive a project while the desktop app has it
open.

## Project File Format

The full annotated layout is shown in [Software design](software_design.md) under "The Project Directory". In short: a
project is a plain directory (`manifest.json`, `draw/setup.py`, `connectivity/associations.json`,
`protocols/main_parameters.py`, one `protocols/<name>.py` per process), and a `.chemunited` file is just that
directory zipped for sharing.

## Orchestrator MCP Server

From the Project menu, **Enable MCP** starts a local MCP server exposing the currently open project's files to
any connected MCP client (such as an AI coding assistant).

<div class="info-block">
<strong>📸 Screenshot needed</strong><br>
Capture: the Project menu's "Enable MCP" toggle, ideally with its tooltip showing the live MCP URL.<br>
Save as: <code>docs/_static/mcp_toggle01.png</code>, then replace this block with:<br>
<code>![Alt text](../_static/mcp_toggle01.png)</code>
</div>

| Tool | Description |
|---|---|
| `list_project_files` | List every file in the currently open project. |
| `read_project_file` | Read the contents of a project file. |
| `write_project_file` | Write/overwrite a project file. |
| `delete_project_file` | Delete a project file. |
| `refresh_project` | Reload the project in the GUI after an external edit. |
| `export_platform_svg` | Export the current platform drawing as an SVG. |

<div class="warning-block">
<strong>⚠️ Warning</strong><br>
MCP is optional and off by default. Enabling it exposes local file/project control to any connected MCP client —
only enable it on trusted machines.
</div>

## Work-Server Backend

There is a separate execution server (`chemunited-workflow`) with its own REST API, MCP tools, and browser
dashboard — used when actually running a protocol against hardware. See
[The Dashboard](../dashboard/overview.md) rather than duplicating that material here.

## Simulation Backend

`chemunited-sim` also runs its own small local FastAPI server, used internally by the **Run Simulation** button —
see [Setup Digital Twins](../simulation/digital_twins.md) for what it does; you do not need to start it manually
for normal use.
