"""Routes: HTML UI pages and HTMX fragment endpoints."""

from __future__ import annotations

import asyncio
import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response

from typing import Any

from ..dependencies import get_project_holder
from ..project_holder import ProjectHolder

router = APIRouter(include_in_schema=False)

_WEB_DIR = Path(__file__).parent.parent.parent / "web"
_WEB_INDEX = _WEB_DIR / "index.html"

# Which index.html gets served (bundled vs. per-project override) depends on
# runtime state, so the response must never be cached by the browser.
_NO_STORE_HEADERS = {"Cache-Control": "no-store"}


def _safe_join(base: Path, filename: str) -> Path | None:
    """Resolve *filename* under *base*, or None if it would escape it."""
    candidate = (base / filename).resolve()
    if not candidate.is_relative_to(base.resolve()):
        return None
    return candidate


def _resolve_index(holder: ProjectHolder) -> Path:
    """Prefer a project-supplied dashboard build over the bundled one."""
    if holder.project_dir is not None:
        override = holder.project_dir / "customizations" / "ui" / "dist" / "index.html"
        if override.is_file():
            return override
    return _WEB_INDEX


# ── Pages ─────────────────────────────────────────────────────────────────────


@router.get("/")
async def dashboard(
    holder: ProjectHolder = Depends(get_project_holder),
) -> FileResponse:
    return FileResponse(_resolve_index(holder), headers=_NO_STORE_HEADERS)


@router.get("/run-control")
@router.get("/protocols")
@router.get("/monitoring")
@router.get("/logs")
@router.get("/devices")
@router.get("/export")
async def vue_page(
    holder: ProjectHolder = Depends(get_project_holder),
) -> FileResponse:
    return FileResponse(_resolve_index(holder), headers=_NO_STORE_HEADERS)


@router.get("/assets/{filename:path}")
async def dashboard_asset(
    filename: str,
    holder: ProjectHolder = Depends(get_project_holder),
) -> FileResponse:
    if holder.project_dir is not None:
        candidate = _safe_join(
            holder.project_dir / "customizations" / "ui" / "dist" / "assets", filename
        )
        if candidate is not None and candidate.is_file():
            return FileResponse(candidate)
    candidate = _safe_join(_WEB_DIR / "assets", filename)
    if candidate is not None and candidate.is_file():
        return FileResponse(candidate)
    raise HTTPException(status_code=404, detail=f"Asset '{filename}' not found.")


# ── HTMX fragments ────────────────────────────────────────────────────────────


@router.get("/ui/fragments/active-run")
async def fragment_active_run(
    holder: ProjectHolder = Depends(get_project_holder),
) -> HTMLResponse:
    run_id = holder.active_run_id()
    if run_id:
        html = (
            f'<span class="badge running">Running: {run_id[:8]}&hellip;'
            f' <a href="/run-control" style="color:inherit">[view]</a></span>'
        )
    else:
        html = '<span class="badge idle">No active run</span>'
    return HTMLResponse(content=html)


@router.get("/ui/fragments/log/{filename}")
async def fragment_log(
    filename: str,
    holder: ProjectHolder = Depends(get_project_holder),
) -> HTMLResponse:
    svc = holder.protocol_service
    if svc is None:
        raise HTTPException(status_code=503, detail="No project loaded.")
    try:
        content = svc.read_log(filename, tail=200)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Log '{filename}' not found.")
    from markupsafe import escape

    return HTMLResponse(content=str(escape(content)))


def _status_badge(r: dict[str, Any]) -> str:
    if r.get("error") == "not configured":
        return '<span class="badge idle">unmapped</span>'
    online = r.get("online", False)
    badge_cls = "finished" if online else "failed"
    latency_ms = r.get("latency_ms")
    latency = f" · {latency_ms} ms" if latency_ms is not None else ""
    text = f"online{latency}" if online else "offline"
    return f'<span class="badge {badge_cls}">{text}</span>'


@router.get("/ui/fragments/ping")
async def fragment_ping(
    holder: ProjectHolder = Depends(get_project_holder),
) -> HTMLResponse:
    svc = holder.protocol_service
    if svc is None:
        raise HTTPException(status_code=503, detail="No project loaded.")
    raw = await asyncio.to_thread(svc.ping_components)
    results = [r.model_dump() if hasattr(r, "model_dump") else r for r in raw]
    if not results:
        return HTMLResponse(content="<p>No components configured.</p>")
    parts = []
    for r in results:
        parts.append(
            f'<span id="status-{r.get("component", "")}" '
            f'hx-swap-oob="innerHTML">{_status_badge(r)}</span>'
        )
    return HTMLResponse(content="".join(parts))


@router.get("/ui/fragments/ping/{component}")
async def fragment_ping_one(
    component: str,
    holder: ProjectHolder = Depends(get_project_holder),
) -> HTMLResponse:
    svc = holder.protocol_service
    if svc is None:
        raise HTTPException(status_code=503, detail="No project loaded.")
    try:
        r = await asyncio.to_thread(svc.ping_component, component)
    except KeyError:
        raise HTTPException(
            status_code=404, detail=f"Component '{component}' not found."
        )
    return HTMLResponse(content=_status_badge(r))


# ── Project-specific static assets ────────────────────────────────────────────


@router.get("/project-static/{filename}")
async def project_static(
    filename: str,
    holder: ProjectHolder = Depends(get_project_holder),
) -> Response:
    if not holder.is_loaded() or holder.project_dir is None:
        raise HTTPException(status_code=404, detail="No project loaded.")
    file_path = _safe_join(
        holder.project_dir / "customizations" / "ui" / "static", filename
    )
    if file_path is None or not file_path.is_file():
        raise HTTPException(
            status_code=404, detail=f"Static file '{filename}' not found."
        )
    mime, _ = mimetypes.guess_type(filename)
    return Response(
        content=file_path.read_bytes(),
        media_type=mime or "application/octet-stream",
    )
