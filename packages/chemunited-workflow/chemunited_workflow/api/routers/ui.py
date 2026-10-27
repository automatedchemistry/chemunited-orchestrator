"""Routes: HTML UI pages, the dashboard customization endpoints (``/ui/...``)
and HTMX fragment endpoints."""

from __future__ import annotations

import asyncio
import mimetypes
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from loguru import logger
from markupsafe import escape

from ..dependencies import get_project_holder
from ..project_holder import ProjectHolder
from ..services.ui_customization import (
    EXTENSION_CONTENT_TYPES,
    load_ui,
    resolve_extension_file,
)

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


def resolve_dashboard_index(holder: ProjectHolder) -> Path:
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
    return FileResponse(resolve_dashboard_index(holder), headers=_NO_STORE_HEADERS)


@router.get("/run-control")
@router.get("/protocols")
@router.get("/monitoring")
@router.get("/logs")
@router.get("/devices")
@router.get("/export")
async def vue_page(
    holder: ProjectHolder = Depends(get_project_holder),
) -> FileResponse:
    return FileResponse(resolve_dashboard_index(holder), headers=_NO_STORE_HEADERS)


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


# ── Dashboard customization (customizations/ui/) ──────────────────────────────


@router.get("/ui/manifest")
async def ui_manifest(
    holder: ProjectHolder = Depends(get_project_holder),
) -> JSONResponse:
    """The loaded project's checked ``ui_hook.py``, which the dashboard applies
    at start-up. Always 200: with no project or no hook it customizes nothing."""
    loaded = await asyncio.to_thread(load_ui, holder.project_dir)
    return JSONResponse(loaded.manifest, headers=_NO_STORE_HEADERS)


@router.get("/ui/ext/{path:path}")
async def ui_extension_file(
    path: str,
    request: Request,
    holder: ProjectHolder = Depends(get_project_holder),
) -> Response:
    """A file under ``customizations/ui/`` (pages, widgets, styles, images).

    Revalidated on every use (ETag), so an edited file shows on the next
    refresh while an unchanged one costs a 304.
    """
    project_dir = holder.project_dir
    file_path = (
        None if project_dir is None else resolve_extension_file(project_dir, path)
    )
    if file_path is None:
        raise HTTPException(status_code=404, detail=f"File '{path}' not found.")
    stat = file_path.stat()
    headers = {
        "ETag": f'"{stat.st_mtime_ns:x}-{stat.st_size:x}"',
        "Cache-Control": "no-cache",
        "X-Content-Type-Options": "nosniff",
    }
    if headers["ETag"] in request.headers.get("if-none-match", ""):
        return Response(status_code=304, headers=headers)
    media_type = EXTENSION_CONTENT_TYPES[file_path.suffix.lower()]
    return FileResponse(file_path, media_type=media_type, headers=headers)


_HTML_PAGE_HEADERS = {
    "Cache-Control": "no-store",
    # Even when opened directly, the page gets an opaque origin: it can't read
    # the dashboard's stored API token or act with the dashboard's rights.
    "Content-Security-Policy": "sandbox allow-scripts",
    "X-Content-Type-Options": "nosniff",
}


@router.get("/ui/html/{path:path}")
def ui_html_page(
    path: str,
    holder: ProjectHolder = Depends(get_project_holder),
) -> HTMLResponse:
    """A page whose HTML an ``HtmlPage.render`` function in ``ui_hook.py`` returns."""
    page = load_ui(holder.project_dir).html_pages.get(f"/{path}")
    if page is None:
        raise HTTPException(status_code=404, detail=f"No HTML page '/{path}'.")
    try:
        html = page.render()
        if not isinstance(html, str):
            raise TypeError(f"render() returned {type(html).__name__}, not str")
    except Exception as exc:
        logger.exception("HTML page '{}' failed to render", page.path)
        body = (
            f"<h1>{escape(page.label)} failed to render</h1>"
            f"<pre>{escape(f'{type(exc).__name__}: {exc}')}</pre>"
        )
        return HTMLResponse(body, status_code=500, headers=_HTML_PAGE_HEADERS)
    return HTMLResponse(html, headers=_HTML_PAGE_HEADERS)


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
