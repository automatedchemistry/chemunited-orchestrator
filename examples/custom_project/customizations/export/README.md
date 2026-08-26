# Custom export example

A working example of the export-customization extension point described in
[`docs/api-reference.md`](../../../../docs/api-reference.md#export).
`export_hook.py` overrides both actions:

- `build_zip` — a "logs-only" export: skips monitoring recordings and
  protocol copies entirely, zipping just the raw log file(s) for the
  selected runs. Shows that a hook can *narrow* what chemunited's default
  export would include, not only add to it.
- `clean` — refuses to delete more than 3 runs in a single call (raises
  `ValueError` otherwise, which the endpoint surfaces as HTTP `500` rather
  than silently doing a partial clean), and appends every deleted log
  filename to `cleaned_runs.log` (next to this file) as an audit trail
  before removing it. Only the log file itself is deleted — monitoring
  recordings and protocols are left alone here, matching `build_zip`'s
  logs-only scope above.

## Try it

```bash
chemunited-workflow serve examples/custom_project
```

List the executed runs available to select from (either via
`GET /export/preview`, or run a protocol first if there are none yet):

```bash
curl http://127.0.0.1:3116/export/preview
```

Download a selection — with this hook installed, the zip contains only the
log file(s), even though the default behavior would also include each run's
monitoring recording and source protocol:

```bash
curl -G http://127.0.0.1:3116/export/download \
  --data-urlencode "log=<a log filename from the preview above>" \
  -o export.zip
unzip -l export.zip
```

Clean a selection — try more than 3 at once to see the safety cap kick in:

```bash
curl -X POST http://127.0.0.1:3116/export/clean \
  -H "Content-Type: application/json" \
  -d '{"logs": ["<filename 1>", "<filename 2>", "<filename 3>", "<filename 4>"]}'
# → 500, "Refusing to clean 4 runs in one call (limit is 3)."
```

Edit `export_hook.py` and call again — it's reloaded fresh on every call, no
server restart needed.

## Layout

```
customizations/export/
├── export_hook.py     # EXPORT_HOOKS = {"build_zip": ..., "clean": ...}
└── cleaned_runs.log   # written by clean() the first time it deletes something
```
