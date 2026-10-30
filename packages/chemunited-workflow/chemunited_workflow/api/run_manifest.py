"""Run manifests: what each run executed, kept next to its log.

``log/manifests/{run_id}.json`` is written when a run starts, with state
``running``, and rewritten when it ends with its outcome and the per-step
results ``GET /run/report`` serves. It holds the exact protocol that ran,
the run's options, the project's git commit (see
``chemunited_workflow.provenance``) and the software versions, so a run can
be traced back to the version of the project that ran it, also after the
work-server restarted or the protocol file was deleted.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from chemunited_workflow.provenance import GitState, software_versions

from .run_store import RunRecord, RunState

MANIFEST_SCHEMA = "chemunited-run-manifest/1"


def manifest_path(project_dir: Path, run_id: str) -> Path:
    return project_dir / "log" / "manifests" / f"{run_id}.json"


def _timestamp(moment: datetime) -> str:
    return moment.astimezone().isoformat(timespec="seconds")


def build_run_manifest(
    *,
    run_id: str,
    started_at: datetime,
    protocol_filename: str,
    protocol: dict[str, Any],
    options: dict[str, Any],
    project_name: str,
    git: GitState | None,
    head_at_start: str | None = None,
) -> dict[str, Any]:
    """The manifest of a run that just started.

    ``git`` is the project's state when it was loaded; ``head_at_start`` is
    HEAD at the run's start, given only when it moved since then.
    """
    project: dict[str, Any] = {
        "name": project_name,
        "git": asdict(git) if git is not None else None,
    }
    if head_at_start is not None:
        project["head_at_start"] = head_at_start
    return {
        "schema": MANIFEST_SCHEMA,
        "run_id": run_id,
        "state": RunState.RUNNING.value,
        "reason": None,
        "started_at": _timestamp(started_at),
        "finished_at": None,
        "protocol": {"filename": protocol_filename, "content": protocol},
        "options": options,
        "project": project,
        "software": dict(software_versions()),
        "results": [],
    }


def finish_run_manifest(manifest: dict[str, Any], record: RunRecord) -> dict[str, Any]:
    """``manifest`` with the outcome of the run ``record`` holds."""
    return {
        **manifest,
        "state": record.state.value,
        "reason": record.cancel_reason,
        "finished_at": _timestamp(datetime.now()),
        "results": [result.model_dump() for result in record.results],
    }


def read_run_manifest(path: Path) -> dict[str, Any] | None:
    """The manifest at ``path``; None without one, or if it can't be read (logged)."""
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("Could not read the run manifest {}: {}", path.name, exc)
        return None
    return data if isinstance(data, dict) else None


def write_run_manifest(path: Path, manifest: dict[str, Any]) -> None:
    """Write ``manifest`` to ``path`` atomically.

    Never raises: a problem writing the manifest is logged, and the run goes on.
    """
    temporary = path.with_name(f"{path.name}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        os.replace(temporary, path)
    except Exception as exc:
        logger.warning("Could not write the run manifest {}: {}", path.name, exc)
