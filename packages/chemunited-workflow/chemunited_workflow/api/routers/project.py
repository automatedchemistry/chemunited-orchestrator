"""Routes: GET /project, PUT /project."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from chemunited_workflow.project_loader import (
    ProjectLoadError,
    format_broken_project_error,
    load_project,
)

from ..dependencies import get_project_holder
from ..project_holder import ProjectHolder
from ..schemas import PlatformDevice, ProjectIn, ProjectOut

router = APIRouter(prefix="/project", tags=["project"])


@router.get("/", response_model=ProjectOut)
async def get_project(holder: ProjectHolder = Depends(get_project_holder)):
    """Return the currently loaded project directory, or null if none is loaded.

    Always returns 200 — use this as a readiness probe.
    """
    pd = holder.project_dir
    return ProjectOut(project_dir=str(pd) if pd is not None else None)


@router.put("/", response_model=ProjectOut)
async def put_project(
    body: ProjectIn,
    holder: ProjectHolder = Depends(get_project_holder),
):
    """Load or switch the active project.

    Rejects with 409 if a run is currently active. The RunStore (and all
    historical run records) is preserved across switches.
    """
    active = holder.active_run_id()
    if active is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot switch project while run '{active}' is active.",
        )

    project_path = Path(body.project_dir).resolve()

    try:
        modules = load_project(project_path)
    except ProjectLoadError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        holder.load(modules)
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=format_broken_project_error(
                exc,
                project_path,
                f"Failed to initialize services for project '{project_path}'",
            ),
        ) from exc
    return ProjectOut(project_dir=str(holder.project_dir))


@router.get("/platform-svg", include_in_schema=False)
async def platform_svg(holder: ProjectHolder = Depends(get_project_holder)) -> Response:
    pd = holder.project_dir
    if pd is None:
        raise HTTPException(status_code=404, detail="No project loaded.")
    svg_path = pd / "draw" / "platform.svg"
    if not svg_path.is_file():
        raise HTTPException(status_code=404, detail="platform.svg not found.")
    return Response(
        content=svg_path.read_text(encoding="utf-8"), media_type="image/svg+xml"
    )


@router.get(
    "/platform-devices",
    response_model=list[PlatformDevice],
    include_in_schema=False,
)
async def platform_devices(
    holder: ProjectHolder = Depends(get_project_holder),
) -> list[PlatformDevice]:
    pd = holder.project_dir
    if pd is None:
        raise HTTPException(status_code=404, detail="No project loaded.")
    devices_path = pd / "draw" / "platform-devices.json"
    if not devices_path.is_file():
        raise HTTPException(status_code=404, detail="platform-devices.json not found.")
    try:
        data = json.loads(devices_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=500, detail="platform-devices.json is malformed."
        ) from exc
    return data.get("devices", [])
