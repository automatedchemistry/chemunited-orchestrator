# chemunited-workflow

[![Pre-commit](https://github.com/automatedchemistry/chemunited-orchestrator/actions/workflows/pre-commit.yml/badge.svg)](https://github.com/automatedchemistry/chemunited-orchestrator/actions/workflows/pre-commit.yml)
[![Security Analysis](https://github.com/automatedchemistry/chemunited-orchestrator/actions/workflows/security.yml/badge.svg)](https://github.com/automatedchemistry/chemunited-orchestrator/actions/workflows/security.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![PyPI](https://img.shields.io/pypi/v/chemunited-workflow.svg)](https://pypi.org/project/chemunited-workflow/)

A NetworkX-based workflow execution engine for conditional automation of chemistry experiments. Designed for hardware-in-the-loop laboratory protocols where operations depend on device responses, physical measurements, and branching conditions.

## Features

- **Conditional DAG execution** with loopbacks and parallel branches
- **Device-centric HTTP clients** for hardware control (pipettes, reactors, pumps, etc.)
- **Thread-safe parallel node execution** via `ThreadPoolExecutor`
- **Physical unit handling** (volumes, temperatures, concentrations) using Pint
- **Multiple deployment modes**: FastAPI REST API, MCP server, or direct Python execution
- **Protocol versioning** with timestamped file history and schema validation
- **Single-run execution model** — only one experiment at a time; `POST /run/` returns HTTP 409 if a run is already active, preventing accidental double-dispatch on physical hardware
- **Browser-based dashboard** (Vue SPA) with live run monitoring, per-node progress bars, log viewer, and device status — its built assets ship with the package, no build step required to use it
- **Human-in-the-loop checkpoints** — a node can pause and wait for an operator to reply on the dashboard before continuing, with a mandatory timeout so a run never blocks forever
- **Customisable per-project dashboard** — drop a pre-built SPA into `{project}/customizations/ui/dist/` to override the bundled UI; falls back automatically when absent
- **Standalone sensor monitoring** — register device variables, start polling sessions independent of protocol runs, and read back time-series profiles

## Documentation

- [Installation](docs/installation.md)
- [Quick Start & Project Structure](docs/quickstart.md)
- [Deployment Modes](docs/deployment.md) — FastAPI, MCP, Windows tray
- [HTML UI](docs/html-ui.md) — dashboard pages, per-project overrides, and how the Vue SPA is built
- [API Reference](docs/api-reference.md)
- [MCP Tools](docs/mcp-tools.md)
- [Concepts](docs/concepts.md) — execution model, physical units, dry-run, human-in-the-loop input
- [Running Tests](docs/contributing.md)

## License

MIT — Automated Chemistry, Max Planck Institute for Colloids and Interfaces.
