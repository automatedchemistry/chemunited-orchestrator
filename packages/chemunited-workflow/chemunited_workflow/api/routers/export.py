"""Routes: GET /export/preview, GET /export/download, POST /export/clean."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from ..dependencies import _NO_PROJECT_MSG, get_project_holder
from ..project_holder import ProjectHolder
from ..schemas import ExportCleanRequest, ExportCleanResult, ExportRow
from ..services import export as export_service

router = APIRouter(prefix="/export", tags=["export"])


def _project_dir(holder: ProjectHolder) -> Path:
    if holder.project_dir is None:
        raise HTTPException(status_code=503, detail=_NO_PROJECT_MSG)
    return holder.project_dir


@router.get("/preview", response_model=list[ExportRow])
async def preview(
    holder: ProjectHolder = Depends(get_project_holder),
):
    """One row per executed run — log file, correlated monitoring recording
    (if any), and source protocol (if it still exists)."""
    return export_service.preview(_project_dir(holder))


@router.get("/download")
async def download(
    log: list[str] = Query(min_length=1),
    holder: ProjectHolder = Depends(get_project_holder),
):
    """Build a zip of the selected runs (log + monitoring recording + source
    protocol) and return it as a file download. Never deletes anything —
    see POST /export/clean for that."""
    project_dir = _project_dir(holder)
    try:
        content = export_service.build_zip(project_dir, log)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    filename = f"{project_dir.name}_export_{datetime.now():%Y-%m-%dT%H-%M-%S}.zip"
    return Response(
        content=content,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/clean", response_model=ExportCleanResult)
async def clean(
    body: ExportCleanRequest,
    holder: ProjectHolder = Depends(get_project_holder),
):
    """Permanently delete the selected runs' log files and monitoring
    recordings. protocols_historic/ is never touched."""
    project_dir = _project_dir(holder)
    try:
        return export_service.clean(project_dir, body.logs)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
