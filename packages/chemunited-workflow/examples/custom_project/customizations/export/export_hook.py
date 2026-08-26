"""Example custom export hook for this project.

See docs/api-reference.md#export. Register "build_zip" and/or "clean" here
to override chemunited's default export/clean behavior for the selected
runs — the frontend and the export service call these instead, no code
change to chemunited_workflow itself.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

_MAX_CLEAN_PER_CALL = 3


def build_zip(project_dir: Path, logs: list[str]) -> bytes:
    """Logs-only export: skip monitoring recordings and protocol copies,
    zip just the raw log files themselves. Demonstrates that a hook can
    narrow what chemunited's default export would include, not only add
    to it.
    """
    log_dir = project_dir / "log"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for filename in logs:
            path = log_dir / filename
            if path.is_file():
                zf.write(path, arcname=filename)
    return buffer.getvalue()


def clean(project_dir: Path, logs: list[str]) -> dict:
    """Safety-capped, audited clean: refuses to delete more than
    ``_MAX_CLEAN_PER_CALL`` runs in one call, and appends every deleted
    filename to cleaned_runs.log (next to this file) before removing it.
    Only deletes the log file itself — monitoring recordings and protocols
    are left alone, matching build_zip's logs-only scope above.
    """
    if len(logs) > _MAX_CLEAN_PER_CALL:
        raise ValueError(
            f"Refusing to clean {len(logs)} runs in one call "
            f"(limit is {_MAX_CLEAN_PER_CALL})."
        )

    log_dir = project_dir / "log"
    audit_path = Path(__file__).parent / "cleaned_runs.log"
    deleted: list[str] = []
    with audit_path.open("a", encoding="utf-8") as audit:
        for filename in logs:
            path = log_dir / filename
            if not path.is_file():
                continue
            path.unlink()
            deleted.append(f"log/{filename}")
            audit.write(f"{filename}\n")

    return {"deleted": deleted, "count": len(deleted)}


EXPORT_HOOKS = {
    "build_zip": build_zip,
    "clean": clean,
}
