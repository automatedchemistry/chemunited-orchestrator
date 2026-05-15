# ChemUnited — Project Storage Design

## Overview

A ChemUnited project lives as a **plain directory** on disk. The directory is the
source of truth. A `.chemunited` file is a compressed export of that directory,
used for sharing and archiving — it is never the working format.

---

## Directory Structure

```
my_experiment/                       ← working directory (source of truth)
│
├── manifest.json                    ← project identity and process order
├── pyproject.toml                   ← makes the project pip-installable
├── __init__.py                      ← top-level package marker
├── main.py                          ← entry point: run the configured sequence
├── api.py                           ← FastAPI server: configure and inspect before running
│
├── .git/                            ← version history (never packed)
├── .gitignore                       ← excludes __pycache__, connectivity, etc.
│
├── draw/
│   ├── setup.py                     ← Python draw setup script
│   └── platform.svg                 ← generated platform drawing export
│
├── protocols/
│   ├── __init__.py                  ← auto-generated process/config registries
│   ├── main_parameters.py           ← MainParameters class, shared across all processes
│   ├── calibration.py               ← one file = one complete process
│   ├── react.py
│   └── clean.py
│
├── protocols_hystoric/
│   └── react_2026-03-27T16-18-00.json ← saved protocol script snapshots
│
└── connectivity/
    └── associations.json            ← device ↔ component mapping (machine-specific)
```

---

## File Descriptions

### `manifest.json`

Project identity. Read on open, updated on every save.

```json
{
  "name": "my_experiment",
  "chemunited_version": "0.1.0",
  "created": "2026-03-27T15:35:00+00:00",
  "last_modified": "2026-03-27T16:18:00+00:00",
  "description": "Photo-oxidation screening",
  "processes_order": ["calibration", "react", "clean"]
}
```

`my_experiment` is the name of the project provided by the user, and it is used to create the
working directory and the `.chemunited` file.

`processes_order` controls the order in which processes appear in the
Protocols and Pre-Running panels.

---

### `main.py`

Entry point for executing the configured protocol. Holds the `MainParameter`
instance and the process sequence, and wires them together before running.

```python
from protocols.main_parameters import MainParameter
from protocols import CONFIGS, PROCESSES

MAIN_PARAMETER = MainParameter()
PROCESSES_INSTANCES = {}

if __name__ == "__main__":
    for process_id in PROCESSES_INSTANCES:
        PROCESSES_INSTANCES[process_id].main_parameter = MAIN_PARAMETER
```

The user edits `MAIN_PARAMETER` fields and `PROCESSES_INSTANCES` directly,
or uses the API server (`api.py`) to configure them before running.

---

### `api.py`

A FastAPI server that exposes HTTP endpoints for configuring and inspecting
the protocol before execution. Generated once at project creation and
portable — it can be run from any location:

```bash
python path/to/my_experiment/api.py
```

Opening `http://localhost:3162` redirects to the interactive Swagger docs.

The server is built on three reusable controllers from `chemunited.workflow.api`:

| Controller | Prefix | Purpose |
|---|---|---|
| `MainParamsController` | `/main-params` | View and update `MainParameter` fields |
| `ProcessesController` | `/processes` | List available process types and their config schemas |
| `SequenceController` | `/sequence` | Build the ordered run list; each entry carries its own config copy |

A dedicated `/report` endpoint returns the full pre-run snapshot — main
parameters, sequence length, and every process config — for inspection before
committing to a run.

---

### `draw/setup.py`

Everything visible on the Draw canvas. ChemUnited generates this Python file
from each component and connection, and calls `build_draw(platform)` when the
project is opened.

```python
def build_draw(platform):
    platform.add_component(
        name="ReagentPump",
        figure="PumpFigure",
        position=(120.0, 340.0),
        angle=0,
        flow_rate="5 ml/min",
    )

    platform.add_connection(
        origin="ReagentPump",
        destiny="ReagentValve",
        origin_port=1,
        destiny_port=1,
        length="100 mm",
        diameter="1.6 mm",
        classification="hydraulic",
    )
```

---

### `draw/platform.svg`

Generated visual export of the current platform drawing. ChemUnited refreshes
this file on project save so the platform can be viewed in external tools
without opening the Qt application.

The SVG is a companion preview only. Project loading still uses
`draw/setup.py` as the source of truth.

---

### `protocols/` — one `.py` file per process

Each process is a **self-contained Python module**. It holds the process
config class, the workflow graph (`build_workflow`), and all node methods
in one place. This matches exactly how `chemunited-workflow` expects a
`Process` subclass to be written.

```
protocols/
├── __init__.py          ← auto-generated, do not edit
├── main_parameters.py   ← shared MainParameters class
├── calibration.py       ← CustomProcess and ProcessConfig
├── react.py             ← CustomProcess and ProcessConfig
└── clean.py             ← CustomProcess and ProcessConfig
```

A process file is generated from the `process.txt` Qt resource template
when the user clicks **New Process**. After creation the user edits it
directly in the script editor or any external IDE.

On project save, ChemUnited treats process files in two modes:
- if `protocols/<process>.py` does not exist yet, it scaffolds a new file
  from the template;
- if the file already exists, it updates the `build_workflow()` method in
  place, preserves workflow-managed methods that still exist, adds default
  stubs for newly introduced workflow methods, removes obsolete
  workflow-managed methods, and leaves unrelated helper methods untouched.

**Class naming convention:** every process file defines the same generic public
class names:

| File | Class |
|---|---|
| `react.py` | `CustomProcess`, `ProcessConfig` |
| `calibration.py` | `CustomProcess`, `ProcessConfig` |
| `my_process.py` | `CustomProcess`, `ProcessConfig` |

---

### `protocols/__init__.py`

Auto-generated by ChemUnited whenever a process is added, removed, or
renamed. **Do not edit manually.**

```python
"""Auto-generated by ChemUnited — do not edit manually."""

from .calibration import CustomProcess as calibrationProcess, ProcessConfig as calibrationConfig
from .react import CustomProcess as reactProcess, ProcessConfig as reactConfig
from .clean import CustomProcess as cleanProcess, ProcessConfig as cleanConfig

PROCESSES = {
    "calibration": calibrationProcess,
    "react": reactProcess,
    "clean": cleanProcess,
}

CONFIGS = {
    "calibration": calibrationConfig,
    "react": reactConfig,
    "clean": cleanConfig,
}
```

ChemUnited imports `PROCESSES` and `CONFIGS` at runtime to discover process
and config classes without any hard-coded knowledge of which processes exist.

---

### `protocols/main_parameters.py`

Shared parameter class available to all processes. Generated once from
the `main_parameters.txt` Qt resource template when the project is
created. The user edits it freely afterwards.

---

### `protocols_hystoric/` — saved protocol JSON files

Protocol script snapshots saved from the Pre-Running panel. Each snapshot is
stored as a JSON file so it can be reopened for summary, monitoring, or
simulation without changing the editable Python process modules in
`protocols/`.

```
protocols_hystoric/
└── react_2026-03-27T16-18-00.json
```

The folder is created with the project and is kept as part of the working
directory structure. JSON files inside it are packed into `.chemunited` exports.

---

### `connectivity/associations.json`

Maps abstract draw components to real FlowChem device endpoints.
This file is **machine-specific** and is excluded from Git by `.gitignore`.
It is still packed into `.chemunited` exports so the file can be
transferred, but the user should always verify associations after
opening a project on a new machine.

```json
{
  "server_url": "http://127.0.0.1:8000",
  "associations": [
    {
      "component": "ReagentPump",
      "component_url": "PumpA/pump"
    },
    {
      "component": "ReagentValve",
      "component_url": "MyKnauer/distribution-valve"
    }
  ]
}
```

---

### `pyproject.toml`

Makes the project directory a pip-installable Python package, with
`chemunited` declared as a dependency. Useful when researchers want to
import their process classes from Jupyter notebooks or external scripts.

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "my-experiment"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["chemunited>=0.1.0"]

[tool.setuptools.packages.find]
where = ["."]
include = ["protocols*"]
```

---

## The `.chemunited` Export File

A `.chemunited` file is a standard ZIP archive containing the project
directory contents, with `.git` and `.gitignore` excluded.

```
my_experiment.chemunited  (ZIP)
├── manifest.json
├── pyproject.toml
├── __init__.py
├── main.py
├── api.py
├── draw/setup.py
├── draw/platform.svg
├── protocols/__init__.py
├── protocols/main_parameters.py
├── protocols/calibration.py
├── protocols/react.py
├── protocols/clean.py
├── protocols_hystoric/react_2026-03-27T16-18-00.json
└── connectivity/associations.json
```

**What is excluded from the ZIP:**

| Excluded | Reason |
|---|---|
| `.git/` | Binary, machine-specific, meaningless on another machine |
| `.gitignore` | Irrelevant outside the working directory |
| `__pycache__/` | Derived, always recomputed |
| `.chemunited_session` | Local session state |

---

## Lifecycle

### New project

```
User clicks New Project
        ↓
Provide project name and working directory
        ↓
Create working directory
Write manifest.json, pyproject.toml, __init__.py
Write main.py  (from template)
Write api.py   (from template, imports chemunited.workflow.api controllers)
Write protocols/__init__.py  (empty PROCESSES and CONFIGS dicts)
Write protocols/main_parameters.py  (from template)
Create protocols_hystoric/  (JSON protocol script snapshots)
Create draw/setup.py  (empty canvas)
Create draw/platform.svg  (generated platform drawing)
Create connectivity/associations.json  (empty)
Init Git repo → first commit "Initialize ChemUnited project"
```

### Open existing project (directory)

```
User selects a directory
        ↓
Load manifest.json
Open Git repo if .git/ present
Load draw/setup.py → call build_draw(platform) and reconstruct ComponentData / EdgeData
Load protocols via import protocols.PROCESSES / protocols.CONFIGS
Ensure protocols_hystoric/ exists
Load connectivity/associations.json
```

### Import `.chemunited` file

```
User opens my_experiment.chemunited
        ↓
If my_experiment/ already contains manifest.json, open that directory
        ↓
Otherwise unpack ZIP → my_experiment/ (next to the .chemunited file)
Load manifest.json
Open existing Git repo, or init fresh Git repo after unpacking
Continue as open existing project
```

### Export `.chemunited` file

```
User clicks Save Protocol Script
        ↓
manifest.json updated (last_modified)
Refresh draw/setup.py and draw/platform.svg
Sync each protocols/<process>.py file in place
Keep protocols_hystoric/*.json files in the working directory/archive
Pack working directory → my_experiment.chemunited
(.git and .gitignore excluded from ZIP)
```

---

## What Is Never Stored

| What | Why |
|---|---|
| `ComponentData` / `EdgeData` objects | Rebuilt by calling `build_draw(platform)` from `setup.py` |
| Compiled `nx.DiGraph` | Rebuilt by `build_workflow()` at runtime |
| `WorkflowExecutor` state | Always restarted |
| Simulation state | Always recomputed |
| Protocol run logs / results | Stored separately in a `runs/` output folder |

`draw/platform.svg` is the one generated companion file stored with the project.
It is refreshed on save for sharing and documentation, but it is never used to
reconstruct the platform.

The principle: **store only what the user authored as load-bearing project
state.** Generated exports such as `draw/platform.svg` are convenience outputs,
not inputs.

---

## Git Integration

The `.git` folder lives in the working directory and is **never** packed
into the `.chemunited` file. When a project is imported from a
`.chemunited` file, a fresh Git repo is initialised — history does not
transfer through the archive.

Auto-commits are created silently on every save:

| User action | Commit message |
|---|---|
| Save Draw canvas | `Update platform layout` (`draw/setup.py` + `draw/platform.svg`) |
| Save process file | `Update process: react` |
| Add new process | `Add process: react` |
| Delete process | `Remove process: react` |
| Save main parameters | `Update main parameters` |

Manual snapshots (user-facing) stage everything and commit with a
user-provided message, producing clean meaningful history entries like:

```
* 8b1d4f2  Optimized flow rate for acceptor step   (today)
* 3c9a7e0  Working calibration — first clean run   (yesterday)
* 1e4c5a9  Initial platform layout                 (3 days ago)
```

`connectivity/associations.json` is excluded from Git by `.gitignore`
because device addresses are machine-specific.

---

## Module Responsibilities

| Module | Responsibility |
|---|---|
| `project/manifest.py` | Read / write `manifest.json` |
| `project/storage.py` | All file I/O — pack, unpack, draw, process sync/update, parameters, connectivity |
| `project/platform_svg.py` | Export the current Qt platform scene to `draw/platform.svg` |
| `project/git_manager.py` | All Git operations — init, commit, snapshot, status, remote |
| `project/session.py` | Single entry point for the GUI — orchestrates storage + Git |
| `project/writer.py` | Generate new `.py` files from Qt resource templates |
| `shared/resources/scripts/process.txt` | Template for new process files |
