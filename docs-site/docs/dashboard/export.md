# Export

**Export** packs the record of past runs into a zip, to archive them, attach them to a lab notebook or share them,
and cleans them out of the project afterwards.

## The Runs Table

The page lists one row per executed run, newest first:

| Column | What it shows |
|--------|---------------|
| **Log** | The run's log file, its size and when it was last written. |
| **Manifest** | The project's git commit the run executed (the first 7 characters; hover for the full one), and whether the project had uncommitted changes. **No commit** means the work-server couldn't read one: git isn't installed, or the project isn't in a git repository. **—** marks a run from before run manifests existed. |
| **Monitoring** | The run's monitoring recording, if it was started with **Record monitoring data** on. |
| **Protocol** | The protocol file the run was started from, if it still exists. |

## Download

Select runs and click **Download selected**. The zip mirrors the project's folders:

```text
export_manifest.json                        index of the runs in this zip and their files
monitoring.db                               every selected run's monitoring readings, as a database
monitoring/<run_id>.csv                     each recorded run's monitoring readings, as a table
log/<protocol>_executed_<time>.log          each run's log
log/manifests/<run_id>.json                 each run's manifest
log/monitoring/<run_id>/*.jsonl             monitoring readings, when recorded
log/monitoring/<run_id>/recording.json      which variable each recorded file holds
protocols_historic/<protocol>.json          the protocol files, when they still exist
```

Downloading never deletes anything.

## Monitoring Data as Tables

A run started with **Record monitoring data** on (see [Run Control](run_control.md)) has its readings in the zip
twice more, ready to open: one CSV per run, and one SQLite database with all the selected runs. Both are made from the
recorded files when you download, so older runs get them too.

### The CSV

`monitoring/<run_id>.csv` has one row per reading, in order of polling, every variable in the same table:

| Column | What it holds |
|--------|---------------|
| `variable` | Which variable: device, command and parameters, e.g. `pump::value` or `adc::read::{"channel":2}`. Filter or pivot on it to get one variable's profile. |
| `component`, `command`, `params` | The same, split up. |
| `tick` | The poll the reading came from. Readings with the same tick were taken together. |
| `time` | When the value was read, with its UTC offset. |
| `value` | The value as read: a number, `true`/`false`, text, or JSON for a list or object. Empty when the read failed. |
| `value_type` | `number`, `boolean`, `string`, `array`, `object` or `null`, so a column of mixed values can be told apart. |
| `unit` | The unit, when the device or custom source returned a quantity. Plain numbers have none. |
| `error` | Why the read failed, if it did. |

The file is comma-separated, with dots for decimals, in UTF-8, so pandas, Origin and LibreOffice open it directly.

<div class="info-block">
<strong>💡 Opening it in Excel</strong><br>
In Excel set to a language that writes decimals with a comma (German or Portuguese, for example), double-clicking
the file puts everything in one column. Use <strong>Data → From Text/CSV</strong> instead, with comma as the
delimiter.
</div>

### The database

`monitoring.db` holds the same readings for all the selected runs, so runs can be compared with a single query. Open it
with [DB Browser for SQLite](https://sqlitebrowser.org/), Python's `sqlite3`, or pandas. Its tables:

| Table | What it holds |
|-------|---------------|
| `runs` | One row per run: protocol, state, start and end, git commit, sample time, and the whole run manifest. |
| `variables` | One row per recorded variable of each run. |
| `readings` | One row per reading. Each value keeps its own type: numbers as numbers, lists and objects as JSON. |
| `readings_long` | A view with the CSV's columns. |

For example, the profile of one variable, and the second element of a list-valued reading:

```sql
SELECT time, value, unit FROM readings_long
WHERE run_id = '<run_id>' AND variable = 'pump::value' ORDER BY tick;

SELECT time, json_extract(value, '$[1]') FROM readings_long
WHERE value_type = 'array';
```

## Clean

**Clean selected** permanently deletes the selected runs' logs, manifests and monitoring recordings. Protocol files
in `protocols_historic/` are never deleted. Download the runs first if you want to keep them.

## Run Manifests

Every run writes `log/manifests/<run_id>.json` when it starts, and completes it when it ends. It records:

| Field | What it holds |
|-------|---------------|
| `protocol` | The protocol's filename and its full content, exactly as it ran, so the run can be repeated even after the protocol file is deleted. |
| `options` | Dry run, command timeout, error resilience and monitoring recording. |
| `started_at`, `finished_at` | When the run started and ended. |
| `state`, `reason` | `finished`, `failed` or `cancelled`, and why a run was stopped, when it was given a reason. |
| `project.git` | The project's `commit` and `branch`, whether it was `dirty`, and the `changed` files. |
| `project.head_at_start` | Present only when the project's commit changed after the work-server loaded it (see below). |
| `software` | The versions of Python and the ChemUnited packages. |
| `results` | The per-step results of the run report: each node's state, result, timing and errors. |

### The Git Commit

ChemUnited doesn't commit anything: versioning a project is up to you (see
[Creating a new project](../wellcome/new_project.md)). When the project folder is in a git repository, its own or one
in a folder above it, and git is installed on the machine running the work-server, the work-server reads the commit
when it loads the project. That is when it imports the project's process code, so it is the code the runs execute.

* When `dirty` is `true`, some project files differed from the commit, and `changed` lists them. Commit before running
  to make the record exact.
* When you commit after the work-server loaded the project, runs still execute the code it loaded. Their manifest then
  also records the new commit as `head_at_start`, and the run log warns about it. Click **Refresh project** at the
  bottom of the sidebar to load the new code and commit.
* What the work-server writes into the project itself never counts as a change: `log/`, `run.lock`, and the
  `__pycache__` folders Python creates when it imports the process code.

<div class="info-block">
<strong>💡 Note</strong><br>
A project can change what the zip contains with <code>customizations/export/export_hook.py</code>. Such a hook
replaces the whole download, so it only includes run manifests if it builds on the default export.
</div>
