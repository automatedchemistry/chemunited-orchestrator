# Deployment Modes

## FastAPI server

The FastAPI server is project-agnostic. You can start it without a project and load one at runtime, or pass a project directory as a shortcut to pre-load it at startup.

```bash
# Start without a project — load one via PUT /project after startup
chemunited-workflow serve --port 3116

# Start with a project pre-loaded (shortcut)
chemunited-workflow serve my_project --port 3116

# Development with auto-reload
chemunited-workflow serve --reload
```

Once running, open `http://127.0.0.1:3116/` in a browser to see the HTML dashboard. The Swagger UI is still available at `/docs`.

### LAN advertisement (mDNS)

Add `--advertise` to make the dashboard reachable from other machines on the same local network. The flag binds the server to `0.0.0.0` and registers an mDNS/Zeroconf record so other devices can discover it by name without knowing the IP address.

```bash
# Install the discovery extra first
pip install -e ".[discovery]"

# Advertise with the auto-generated name 'ChemUnited @ <hostname>'
chemunited-workflow serve my_project/ --advertise

# Use a custom name visible in network discovery
chemunited-workflow serve my_project/ --advertise --advertise-name "Flow Synthesis Lab"
```

Expected output:
```
mDNS: advertising 'Flow Synthesis Lab' -> http://192.168.1.42:3116/
INFO:     Uvicorn running on http://0.0.0.0:3116
```

Other machines on the LAN can then open `http://<hostname>.local:3116/` in a browser. The mDNS record is withdrawn cleanly when the server stops (Ctrl-C).

> **Note:** No authentication is included. Anyone on the local network can reach the full API. Use only on trusted networks.

To load or switch projects at runtime:

```bash
curl -X PUT http://127.0.0.1:3116/project/ \
  -H "Content-Type: application/json" \
  -d '{"project_dir": "/absolute/path/to/my_project"}'
```

> **Windows paths:** Use forward slashes (`C:/Users/...`) or escaped backslashes (`C:\\Users\\...`) in JSON — bare backslashes are not valid JSON.

You can switch to a different project at any time, as long as no run is currently active.

> **CLI change (v0.0.1+):** The server is now a subcommand — use `chemunited-workflow serve [options]`. Running bare `chemunited-workflow` (no arguments) still starts the FastAPI server with default settings.

## FastAPI + MCP on the same port

Add `--with-mcp` to expose both the browser dashboard and the MCP streamable-HTTP endpoint from a single server process on a single port. Both share the same project state — loading a project via the dashboard makes it immediately visible to MCP tools and vice versa.

```bash
chemunited-workflow serve my_project/ --with-mcp
```

| Endpoint | Address |
|---|---|
| Dashboard / REST API | `http://127.0.0.1:3116/` |
| MCP streamable HTTP | `http://127.0.0.1:3116/mcp` |

## System tray

Add `--tray` to run the server minimised to the Windows system tray. uvicorn starts in a background thread; the main thread runs the tray icon loop.

```bash
chemunited-workflow serve my_project/ --tray
```

Add `--silent` to detach from the terminal so no console window stays open. The process calls `FreeConsole()` to release the console immediately after startup:

```bash
chemunited-workflow serve my_project/ --tray --silent
```

`--silent` requires `--tray` and only has an effect on Windows.

The tray menu provides:

- **Open App**: opens the dashboard in the default browser.
- **Status**: shows a notification that the server is running.
- **Quit**: stops the server and removes the tray icon.

`--tray` is incompatible with `--reload`.

## Full combination

All flags are independent and compose freely:

```bash
chemunited-workflow serve my_project/ \
  --advertise \
  --advertise-name "Flow Synthesis Lab" \
  --with-mcp \
  --tray \
  --silent
```

This starts the dashboard and the MCP endpoint on the same port, advertises via mDNS, runs minimised to the tray, and leaves no terminal window open.

---

For available HTTP endpoints see [API Reference](api-reference.md). For MCP tool definitions see [MCP Tools](mcp-tools.md).

[← Back to README](../README.md)
