# Custom routes example

A working example of the custom-router extension point described in
[`docs/api-reference.md`](../../../../docs/api-reference.md#custom-routes).
`router_hook.py` registers three named actions:

- `residence_time_min` — a pure computation over its own kwargs
  (`reactor_volume_ml / flow_rate_ml_min`), no device involved.
- `chiller_temperature_f` — reads the real `chiller`/`temperature` component
  through `CustomRouteContext.platform`, converted to Fahrenheit. A
  throwaway Platform is opened just for this call and closed once it
  returns — it does not share the monitoring poll loop's connection.
- `set_chiller_setpoint` — drives the real `chiller` component. Demonstrates
  that a custom route can have a side effect, not just report a value.

## Try it

```bash
chemunited-workflow serve examples/custom_project
```

List the registered routes (either via `GET /custom/discover`, or the
`discover_custom_routes` MCP tool):

```bash
curl http://127.0.0.1:3116/custom/discover
# → [{"name": "residence_time_min", "parameters": [...]},
#    {"name": "chiller_temperature_f", "parameters": []},
#    {"name": "set_chiller_setpoint", "parameters": [...]}]
```

Call one — the request body is passed through as keyword arguments:

```bash
curl -X POST http://127.0.0.1:3116/custom/residence_time_min \
  -H "Content-Type: application/json" \
  -d '{"flow_rate_ml_min": 2.5, "reactor_volume_ml": 10.0}'
# → {"name": "residence_time_min", "ok": true, "result": 4.0, "error": null, "latency_ms": 1}

curl -X POST http://127.0.0.1:3116/custom/chiller_temperature_f -d '{}'
curl -X POST http://127.0.0.1:3116/custom/set_chiller_setpoint -d '{"celsius": 15}'
```

An unregistered name returns 404. An exception raised *inside* a registered
function doesn't fail the HTTP call — it comes back as `"ok": false` with
`"error"` set, same as calling a broken device command.

Edit `router_hook.py` and call again — it's reloaded fresh on every call, no
server restart needed.

## Layout

```
customizations/routers/
└── router_hook.py   # CUSTOM_ROUTES = {"residence_time_min": ..., "chiller_temperature_f": ..., "set_chiller_setpoint": ...}
```
