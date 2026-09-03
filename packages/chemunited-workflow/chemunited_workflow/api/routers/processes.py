"""Routes: GET /processes, GET /processes/{name}/source,
GET /processes/{name}/schema, GET /processes/{name}/diagram.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from ..dependencies import get_project_holder, get_protocol_service
from ..project_holder import ProjectHolder
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


@router.get("/{name}/diagram", include_in_schema=False)
async def get_process_diagram(
    name: str,
    holder: ProjectHolder = Depends(get_project_holder),
) -> Response:
    """Return this process's workflow diagram as a pre-generated SVG.

    The diagram is exported from the orchestrator app's canvas on project
    save (``draw/workflows/{name}.svg``) — it is not rendered live here.
    404 if the project hasn't been saved since this process was added.
    """
    pd = holder.project_dir
    if pd is None:
        raise HTTPException(status_code=404, detail="No project loaded.")
    workflows_dir = (pd / "draw" / "workflows").resolve()
    svg_path = (workflows_dir / f"{name}.svg").resolve()
    if not svg_path.is_relative_to(workflows_dir):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid process name {name!r}: path traversal is not allowed.",
        )
    if not svg_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"No diagram found for process {name!r}. Save the project to generate it.",
        )
    return Response(
        content=svg_path.read_text(encoding="utf-8"), media_type="image/svg+xml"
    )
