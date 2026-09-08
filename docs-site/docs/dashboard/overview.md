# Dashboard

The **Dashboard** is the browser-based web app served by the work-server (`chemunited-workflow`) alongside its
REST/MCP API. It's how you interact with a project — start runs, build protocols, watch live data, and check
connectivity — from any browser, without the desktop orchestrator app open. Start it from the desktop app's
[Dashboard Launcher](launcher.md), or run `chemunited-workflow serve` directly; either way it opens at
`http://127.0.0.1:<port>/` (default port `3116`).

The dashboard has six pages, reachable from the sidebar on the left of every page:

* **Dashboard** (this page) — project status at a glance and quick navigation.
* **[Run Control](run_control.md)** — start or cancel a run, and watch it execute live.
* **[Protocols](protocols.md)** — assemble processes into a saved, repeatable protocol.
* **[Monitoring](monitoring.md)** — poll live device variables outside of a run.
* **[Logs](logs.md)** — browse and tail execution log files.
* **[Devices](devices.md)** — check connectivity for every component in the project.

At the bottom of the sidebar: **Refresh project** (reload project state from disk), **API Docs** (opens the
work-server's OpenAPI docs — see [API & MCP Tools](api_and_mcp.md)), and a **Dark theme** toggle.

## Landing page

![Alt text](../_static/dashboard_overview.png)

Four cards summarize the loaded project:

| Card | Shows |
|---|---|
| **Project** | The project's name and its folder path on disk. |
| **Protocols** | How many protocol files are saved, and when the most recent one was saved. |
| **Processes** | How many processes are registered in the project. |
| **Run Status** | Whether a run is currently active, or `No runs recorded yet`. |

**Refresh** re-reads all four cards from the server. Below them, the **Platform** card renders the project's
platform diagram (the same layout you build in [Drawing](../drawing/drawing.md)), useful for a quick visual sanity
check of the loaded setup. At the bottom, four quick-navigation cards jump straight to Run Control, Protocols,
Monitoring, and Logs.

## Starting the work-server manually

You do not need to start the work-server yourself for a normal run — the orchestrator launches it automatically
when you click **Run Monitoring**, and the [Dashboard Launcher](launcher.md) covers the common desktop-side
options. This section is for running it standalone (e.g. headless, on a lab server, or exposed to other machines
on the network), via its own command-line tool:

```bash
chemunited-workflow serve [project_dir] [OPTIONS]
```

Running the bare `chemunited-workflow` command with no arguments is equivalent to `serve` with defaults.

| Flag | Description |
|---|---|
| `--host` | Interface to bind to (defaults to localhost-only). |
| `--port` | Port to serve the dashboard/API on. |
| `--reload` | Auto-restart the server on code changes (development use). |
| `--advertise` | Bind to all interfaces and announce the server on the local network via mDNS/Zeroconf, so it can be discovered by other machines. |
| `--advertise-name` | Custom name to advertise the server as, when `--advertise` is used. |
| `--token` | Bearer token remote (non-loopback) clients must present for state-changing requests (defaults to `$CHEMUNITED_API_TOKEN`; prefer the env var over the flag to keep it out of shell history and process listings). Loopback callers and read-only requests are never gated. |
| `--with-mcp` | Expose the [MCP tool interface](api_and_mcp.md) on the same port as the dashboard. |
| `--tray` | Run the server in the background with a system-tray icon (Windows), with quick actions to open the dashboard, check status, or quit. |
| `--silent` | Detach the console window. Requires `--tray`, and is not compatible with `--reload`. |

<div class="warning-block">
<strong>⚠️ Warning</strong><br>
Read-only endpoints (monitoring, logs, status) are always open to anyone who can reach the server. State-changing
requests (start/cancel a run, load a project, send device commands, ...) are allowed unconditionally from
<code>127.0.0.1</code>/<code>::1</code>, and from any other address only with a matching
<code>Authorization: Bearer &lt;token&gt;</code> header — set it with <code>--token</code> or
<code>CHEMUNITED_API_TOKEN</code>. Without a token, remote clients started via <code>--advertise</code> (or a
non-localhost <code>--host</code>) can still <em>view</em> the dashboard but cannot change anything. Only expose an
untokened server to a fully trusted lab network.
</div>

## Next steps

See [API & MCP Tools](api_and_mcp.md) if you want to script or automate against the dashboard directly.
