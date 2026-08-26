"""Routes: GET /custom/discover, POST /custom/{name}."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException

from ..dependencies import _NO_PROJECT_MSG, get_project_holder
from ..project_holder import ProjectHolder
from ..schemas import CustomRouteInfo, CustomRouteResult
from ..services.custom_routes import call_custom_route, discover_custom_routes

router = APIRouter(prefix="/custom", tags=["custom"])


@router.get("/discover", response_model=list[CustomRouteInfo])
async def discover_routes(
    holder: ProjectHolder = Depends(get_project_holder),
):
    """List the custom routes registered in this project's
    customizations/routers/router_hook.py, with parameter hints introspected
    from each function's signature.
    """
    if holder.project_dir is None:
        raise HTTPException(status_code=503, detail=_NO_PROJECT_MSG)
    return discover_custom_routes(holder.project_dir)


@router.post("/{name}", response_model=CustomRouteResult)
async def call_route(
    name: str,
    body: dict[str, Any] = Body(default_factory=dict),
    holder: ProjectHolder = Depends(get_project_holder),
):
    """Call a registered custom route by name, with the request body passed
    through as keyword arguments.

    Returns 404 if `name` isn't registered. An exception raised by the
    registered function itself is not a 404/500 — it comes back as
    `ok: false` with `error` set, the same "the call succeeded, the action
    failed" contract used by the component command endpoint.
    """
    if holder.project_dir is None:
        raise HTTPException(status_code=503, detail=_NO_PROJECT_MSG)
    try:
        return call_custom_route(holder.project_dir, name, body)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
