"""Routes: GET /processes, GET /processes/{name}/schema."""

from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import get_protocol_service
from ..schemas import ProcessSource
from ..services.protocol import ProtocolService

router = APIRouter(prefix="/processes", tags=["processes"])


@router.get("/")
async def list_processes(svc: ProtocolService = Depends(get_protocol_service)):
    """List all registered processes.

    Returns every process available in this experiment together with its
    human-readable description and the JSON Schema of its configuration model.
    Call this first to discover what processes can be added to a snapshot.
    """
    return svc.list_processes()


@router.get("/{name}/source", response_model=ProcessSource)
async def get_process_source(
    name: str,
    svc: ProtocolService = Depends(get_protocol_service),
):
    """Return the full source code of a process definition file."""
    try:
        source = svc.read_process(name)
        return ProcessSource(name=name, source=source)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/{name}/schema")
async def get_process_schema(
    name: str,
    svc: ProtocolService = Depends(get_protocol_service),
):
    """Return the full parameter schema for a single process.

    Includes the `config_schema` (process-specific parameters) and the
    `main_parameter_schema` (experiment-level parameters shared across all
    processes). Each field may carry `group`, `editable`, and `visible` hints
    inside `json_schema_extra`.
    """
    try:
        return svc.get_process_schema(name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
