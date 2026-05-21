# ChemUnited MCP Client Configuration

ChemUnited exposes the current project through a local MCP server when **Project >
Enable MCP** is enabled in the application.

The server uses **Streamable HTTP** at the `/mcp` endpoint. It does not use the
legacy SSE transport.

## Endpoint

The default URL is:

```text
http://127.0.0.1:8765/mcp
```

If port `8765` is busy, ChemUnited automatically tries the next available port up
to `8799`. Use the exact URL shown in the ChemUnited MCP tooltip.

## Streamable HTTP Config

Most MCP clients that support Streamable HTTP can be configured like this:

```json
{
  "mcpServers": {
    "chemunited-project": {
      "type": "streamable-http",
      "url": "http://127.0.0.1:8765/mcp"
    }
  }
}
```

Some clients use `transport` instead of `type`:

```json
{
  "mcpServers": {
    "chemunited-project": {
      "transport": "streamable-http",
      "url": "http://127.0.0.1:8765/mcp"
    }
  }
}
```

## Stdio-Only Clients

If the LLM client only supports stdio MCP servers, use an HTTP-to-stdio MCP proxy,
for example:

```json
{
  "mcpServers": {
    "chemunited-project": {
      "command": "mcp-remote",
      "args": ["http://127.0.0.1:8765/mcp"]
    }
  }
}
```

Install and configure the proxy according to the MCP client you are using.

## Localhost Caveat

`127.0.0.1` only works when the LLM client runs on the same machine and in the
same network namespace as ChemUnited.

If the LLM client runs in Docker, WSL, a VM, another computer, or the cloud,
`127.0.0.1` points to the client environment, not to ChemUnited. In that case,
use a reachable host address or a tunnel instead:

```json
{
  "mcpServers": {
    "chemunited-project": {
      "type": "streamable-http",
      "url": "http://192.168.1.50:8765/mcp"
    }
  }
}
```

ChemUnited currently binds the MCP server to `127.0.0.1`, so remote access may
require changing the server host binding or using a local forwarding/tunneling
tool.

## Troubleshooting

- A browser `GET` request to `/mcp` can return `406 Not Acceptable`; this is
  expected for Streamable HTTP MCP. Use an MCP client, not a plain browser page.
- Confirm that the configured port matches the URL shown by ChemUnited.
- If tool listing works but `refresh_project()` times out, the Qt main thread may
  be blocked. Project file tools such as `list_project_files()` and
  `read_project_file()` do not require the Qt main-thread bridge.
- If all MCP calls time out, first check whether the LLM client can reach the
  ChemUnited host and whether it supports Streamable HTTP.
