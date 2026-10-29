# Export

**Export** packs the record of past runs into a zip, to archive them, attach them to a lab notebook or share them,
and cleans them out of the project afterwards.

## The Runs Table

The page lists one row per executed run, newest first:

| Column | What it shows |
|--------|---------------|
| **Log** | The run's log file, its size and when it was last written. |
| **Manifest** | The project's git commit the run executed (the first 7 characters; hover for the full one), and whether the project had uncommitted changes. **No commit** means the work-server couldn't read one: git isn't installed, or the project isn't in a git repository. **—** marks a run from before run manifests existed. |
| **Monitoring** | The run's monitoring recording, if it was started with recording on. |
| **Protocol** | The protocol file the run was started from, if it still exists. |

## Download

Select runs and click **Download selected**. The zip mirrors the project's folders:

```text
export_manifest.json                        index of the runs in this zip and their files
log/<protocol>_executed_<time>.log          each run's log
log/manifests/<run_id>.json                 each run's manifest
log/monitoring/<run_id>/*.jsonl             monitoring readings, when recorded
protocols_historic/<protocol>.json          the protocol files, when they still exist
```

Downloading never deletes anything.

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
