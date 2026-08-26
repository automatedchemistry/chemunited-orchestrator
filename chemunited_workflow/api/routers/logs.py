"""Routes: GET /logs, GET /logs/{filename}."""

from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import get_protocol_service
from ..schemas import LogSearchResult
from ..services.protocol import ProtocolService

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("/")
async def list_logs(svc: ProtocolService = Depends(get_protocol_service)):
    """List all execution log files.

    Returns metadata (filename, last-modified timestamp, size) for every
    `.log` file in the project's `log/` directory, sorted most-recent first.
    """
    return svc.list_logs()


@router.get("/search", response_model=list[LogSearchResult])
async def search_logs(
    query: str,
    max_results: int = 50,
    svc: ProtocolService = Depends(get_protocol_service),
):
    """Search all active log files for lines containing *query* (case-insensitive)."""
    return svc.search_logs(query, max_results=max_results)


@router.get("/{filename}")
async def read_log(
    filename: str,
    tail: int | None = None,
    svc: ProtocolService = Depends(get_protocol_service),
):
    """Read the contents of a log file.

    Returns the full text of the log. Pass `?tail=N` to return only the last
    N lines — useful for checking recent activity without loading the entire
    file.
    """
    try:
        return {"content": svc.read_log(filename, tail=tail)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
