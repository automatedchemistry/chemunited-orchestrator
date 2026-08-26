# Custom monitoring sources example

This is a working example of the `component: "custom"` pseudo-device described in
[`docs/api-reference.md`](../../../../docs/api-reference.md#custom-sources).
`monitoring_hook.py` registers three Python functions as monitoring variables:

- `residence_time_min` — a *derived* reading (`reactor_volume_ml / flow_rate_ml_min`),
  computed from the variable's own `kwargs` in `connectivity/monitoring.json`, no device
  involved.
- `room_humidity_pct` — a purely synthetic reading, no formula and no device behind it
  at all, standing in for a sensor this project has no driver for.
- `chiller_temperature_f` — reads the real `chiller`/`temperature` component through
  `MonitoringContext.platform` and converts to Fahrenheit. Demonstrates a custom source
  that derives its value from a live device reading, sharing that device's client/lock
  instead of opening a second connection to it.

## Try it

```bash
chemunited-workflow serve examples/custom_project
```

Register the custom variables (either via the dashboard's Monitoring page — "custom" is
selectable in the Component picker — or via `PUT /monitoring/config`):

```bash
curl -X PUT http://127.0.0.1:3116/monitoring/config \
  -H "Content-Type: application/json" \
  -d '{
    "sample_time": 5.0,
    "request_timeout": 5.0,
    "variables": [
      {"component": "chiller", "command": "temperature", "kwargs": {}},
      {"component": "custom", "command": "residence_time_min",
       "kwargs": {"flow_rate_ml_min": 2.5, "reactor_volume_ml": 10.0}},
      {"component": "custom", "command": "room_humidity_pct", "kwargs": {}},
      {"component": "custom", "command": "chiller_temperature_f", "kwargs": {}}
    ]
  }'

curl -X POST http://127.0.0.1:3116/monitoring/start
curl http://127.0.0.1:3116/monitoring/latest
```

`custom::residence_time_min`, `custom::room_humidity_pct`, and
`custom::chiller_temperature_f` show up in the response alongside `chiller::temperature`
— same shape, same endpoints, polled on the same schedule, with no changes to
`chemunited_workflow` itself.

Discovery lists the registered function names instead of querying a device:

```bash
curl http://127.0.0.1:3116/monitoring/discover/custom
# → [{"command": "residence_time_min", ...}, {"command": "room_humidity_pct", ...},
#    {"command": "chiller_temperature_f", ...}]
```

Edit `monitoring_hook.py`, then `POST /monitoring/stop` and `POST /monitoring/start`
again — the file is reloaded fresh every time monitoring turns on, no server restart
needed.

## Layout

```
customizations/monitoring/
└── monitoring_hook.py   # CUSTOM_SOURCES = {"residence_time_min": ..., "room_humidity_pct": ..., "chiller_temperature_f": ...}
```
