"""Routes: GET/POST/DELETE /protocols."""

from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import get_protocol_service
from ..schemas import ProtocolIn
from ..services.protocol import ProtocolService

read_router = APIRouter(prefix="/protocols", tags=["protocols"])
write_router = APIRouter(prefix="/protocols", tags=["protocols"])


@read_router.get("/")
async def list_protocols(svc: ProtocolService = Depends(get_protocol_service)):
    """List all protocol files.

    Returns metadata (filename, last-modified timestamp, size) for every JSON
    file in `protocols_historic/`, sorted most-recent first. Use the filename
    from this list to start a run or inspect a protocol's contents.
    """
    return svc.list_protocols()


@read_router.get("/{filename}")
async def get_protocol(
    filename: str,
    svc: ProtocolService = Depends(get_protocol_service),
):
    """Read a single protocol by filename.

    Returns the full JSON content of the protocol — `main_parameter` plus one
    key per process step in `{process_name}_{index}` format. The insertion
    order of the process keys defines the execution sequence.
    """
    try:
        return svc.read_protocol(filename)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@write_router.post("/", status_code=201)
async def create_protocol(
    body: ProtocolIn,
    svc: ProtocolService = Depends(get_protocol_service),
):
    """Save a new protocol file.

    Validates all process configs and the `main_parameter` block, then writes
    a timestamped JSON file to `protocols_historic/`. Every call creates a
    **new** file — protocols are immutable once written. Returns the generated
    filename, e.g. `suzuki_batch_14_2026-05-15T10-38-00.json`.
    """
    try:
        filename = svc.write_protocol(body.name, body.data)
        return {"filename": filename}
    except (ValueError, Exception) as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@write_router.delete("/{filename}", status_code=204)
async def delete_protocol(
    filename: str,
    svc: ProtocolService = Depends(get_protocol_service),
):
    """Delete a protocol file.

    Permanently removes the file from `protocols_historic/`. This action is
    irreversible. Only available in builder mode (`enable_builder=True`).
    """
    try:
        svc.delete_protocol(filename)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
