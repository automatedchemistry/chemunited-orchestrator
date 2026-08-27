"""Export — one row per executed run (log -> monitoring recording -> source
protocol), zipped up for download or deleted ("cleaned") on request.

A run's three artifacts are correlated purely by filename convention, not an
explicit stored link:

- ``log/{protocol_stem}_executed_{timestamp}.log`` is written by
  ``chemunited_workflow.terminal.create_run_log_path`` — the only writer of
  files under ``log/``.
- ``log/monitoring/{protocol_stem}_{timestamp}/`` is the matching monitoring
  recording directory (``run_id = f"{protocol_stem}_{timestamp}"``, see
  ``api/services/monitoring.py``).
- ``protocols_historic/{protocol_stem}.json`` is the source protocol.

A log filename is therefore enough, on its own, to derive the other two. Rows
are keyed by log filename (not by protocol name) because the same protocol
can be run more than once, each execution producing its own log.

Per-project customization mirrors the ``customizations/routers/router_hook.py``
pattern: an optional ``customizations/export/export_hook.py`` exporting an
``EXPORT_HOOKS`` dict can override ``build_zip`` and/or ``clean``
independently, each taking the selected log filenames. See
docs/api-reference.md#export.
"""

from __future__ import annotations

import importlib.util
import io
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from loguru import logger

_LOG_PATTERN = re.compile(
    r"^(?P<stem>.+)_executed_(?P<timestamp>\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2})\.log$"
)


def _log_dir(project_dir: Path) -> Path:
    return project_dir / "log"


def _monitoring_dir(project_dir: Path) -> Path:
    return project_dir / "log" / "monitoring"


def _protocol_dir(project_dir: Path) -> Path:
    return project_dir / "protocols_historic"


def _log_files(project_dir: Path) -> list[Path]:
    return sorted(
        _log_dir(project_dir).glob("*.log"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def _entry(path: Path, filename: str) -> dict[str, Any]:
    stat = path.stat()
    return {
        "filename": filename,
        "size_bytes": stat.st_size,
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
    }


def _parse_log_filename(filename: str) -> tuple[str, str] | None:
    """Return (protocol_stem, run_id) for a well-formed run-log filename, or
    None if it doesn't match the convention from create_run_log_path."""
    m = _LOG_PATTERN.match(filename)
    if m is None:
        return None
    stem = m.group("stem")
    run_id = f"{stem}_{m.group('timestamp')}"
    return stem, run_id


def _resolve_log(project_dir: Path, filename: str) -> Path | None:
    """Resolve *filename* under log/, guarding against path traversal.
    Returns None if it would escape log/ or doesn't exist."""
    log_dir = _log_dir(project_dir).resolve()
    candidate = (log_dir / filename).resolve()
    if not candidate.is_relative_to(log_dir) or not candidate.is_file():
        return None
    return candidate


def _monitoring_group(project_dir: Path, run_id: str) -> dict[str, Any] | None:
    run_dir = _monitoring_dir(project_dir) / run_id
    if not run_dir.is_dir():
        return None
    files = sorted(run_dir.glob("*.jsonl"))
    if not files:
        return None
    return {
        "run_id": run_id,
        "files": [_entry(p, f"{run_id}/{p.name}") for p in files],
        "total_size_bytes": sum(f.stat().st_size for f in files),
    }


def _protocol_entry(project_dir: Path, stem: str) -> dict[str, Any] | None:
    path = _protocol_dir(project_dir) / f"{stem}.json"
    if not path.is_file():
        return None
    return _entry(path, path.name)


def preview(project_dir: Path) -> list[dict[str, Any]]:
    """One row per log file, most-recent first, each correlated (by filename
    convention) with its monitoring recording and source protocol, if any
    still exist."""
    rows = []
    for log_path in _log_files(project_dir):
        row: dict[str, Any] = {
            "log": _entry(log_path, log_path.name),
            "monitoring": None,
            "protocol": None,
        }
        parsed = _parse_log_filename(log_path.name)
        if parsed is not None:
            stem, run_id = parsed
            row["monitoring"] = _monitoring_group(project_dir, run_id)
            row["protocol"] = _protocol_entry(project_dir, stem)
        rows.append(row)
    return rows


def default_build_zip(project_dir: Path, logs: list[str]) -> bytes:
    """Zip the selected runs' log + monitoring recording + source protocol.
    Pure read — never deletes anything. Unknown/missing filenames in *logs*
    are skipped silently. A protocol shared by two selected runs is written
    only once."""
    buffer = io.BytesIO()
    written: set[str] = set()

    def add(path: Path, arcname: str) -> None:
        if arcname in written:
            return
        zf.write(path, arcname=arcname)
        written.add(arcname)

    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for filename in logs:
            log_path = _resolve_log(project_dir, filename)
            if log_path is None:
                continue
            add(log_path, f"log/{log_path.name}")

            parsed = _parse_log_filename(log_path.name)
            if parsed is None:
                continue
            stem, run_id = parsed

            run_dir = _monitoring_dir(project_dir) / run_id
            if run_dir.is_dir():
                for jsonl in sorted(run_dir.glob("*.jsonl")):
                    add(jsonl, f"log/monitoring/{run_id}/{jsonl.name}")

            protocol_path = _protocol_dir(project_dir) / f"{stem}.json"
            if protocol_path.is_file():
                add(protocol_path, f"protocols_historic/{protocol_path.name}")

    return buffer.getvalue()


def default_clean(project_dir: Path, logs: list[str]) -> dict[str, Any]:
    """Delete the selected runs' log file and monitoring recording. Never
    touches protocols_historic/ — protocols are always copied, never
    removed. Unknown/missing filenames in *logs* are skipped silently."""
    deleted: list[str] = []

    for filename in logs:
        log_path = _resolve_log(project_dir, filename)
        if log_path is None:
            continue
        log_path.unlink()
        deleted.append(f"log/{log_path.name}")

        parsed = _parse_log_filename(filename)
        if parsed is None:
            continue
        _, run_id = parsed
        run_dir = _monitoring_dir(project_dir) / run_id
        if run_dir.is_dir():
            for jsonl in sorted(run_dir.glob("*.jsonl")):
                deleted.append(f"log/monitoring/{run_id}/{jsonl.name}")
            shutil.rmtree(run_dir)

    return {"deleted": deleted, "count": len(deleted)}


def load_export_hooks(project_dir: Path) -> dict[str, Callable[..., Any]]:
    """Load EXPORT_HOOKS from the project's export hook file, if any.

    Never raises: a missing file yields an empty registry silently (the hook
    is optional); a file that fails to import or doesn't export an
    EXPORT_HOOKS dict is logged and also yields an empty registry — a broken
    hook must never take the endpoint down, matching the same convention
    used for CUSTOM_ROUTES and CUSTOM_SOURCES.
    """
    path = project_dir / "customizations" / "export" / "export_hook.py"
    if not path.exists():
        return {}
    try:
        spec = importlib.util.spec_from_file_location("export_hook", path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot create a module spec from {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        hooks = getattr(module, "EXPORT_HOOKS", None)
        if not isinstance(hooks, dict):
            raise AttributeError("export_hook.py does not export an EXPORT_HOOKS dict")
        return hooks
    except Exception:
        logger.exception("Failed to load export hooks from {}", path)
        return {}


def build_zip(project_dir: Path, logs: list[str]) -> bytes:
    """Build the export zip for the selected runs, using the project's
    ``build_zip`` hook if registered, otherwise the default. A registered
    hook's own exception is not swallowed — it propagates to the caller,
    which turns it into an error response.
    """
    hooks = load_export_hooks(project_dir)
    hook = hooks.get("build_zip")
    if hook is not None:
        return hook(project_dir, logs)
    return default_build_zip(project_dir, logs)


def clean(project_dir: Path, logs: list[str]) -> dict[str, Any]:
    """Delete the selected runs' source files, using the project's ``clean``
    hook if registered, otherwise the default. A registered hook's own
    exception is not swallowed — it propagates to the caller.
    """
    hooks = load_export_hooks(project_dir)
    hook = hooks.get("clean")
    if hook is not None:
        return hook(project_dir, logs)
    return default_clean(project_dir, logs)
