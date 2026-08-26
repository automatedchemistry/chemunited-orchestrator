"""chemunited_workflow.api — FastAPI application factory."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .dependencies import get_project_holder
from .project_holder import ProjectHolder
from .routers.components import router as components_router
from .routers.custom import router as custom_router
from .routers.export import router as export_router
from .routers.logs import router as logs_router
from .routers.monitoring import router as monitoring_router
from .routers.processes import router as processes_router
from .routers.project import router as project_router
from .routers.protocols import read_router as protocols_read_router
from .routers.protocols import write_router as protocols_write_router
from .routers.runner import router as runner_router
from .routers.ui import router as ui_router

_WEB_DIR = Path(__file__).parent.parent / "web"


def create_api(
    *,
    with_mcp: bool = False,
    host: str = "127.0.0.1",
    port: int = 3116,
) -> FastAPI:
    """Create and return a configured FastAPI application.

    The server starts with no project loaded. Use ``PUT /project`` to load a
    project directory at runtime.

    Pass ``with_mcp=True`` to also mount an MCP streamable-HTTP endpoint at
    ``/mcp`` sharing the same ``ProjectHolder``.
    """
    holder = ProjectHolder()

    mcp_session_manager = None
    mcp_sub_app = None

    if with_mcp:
        from chemunited_workflow.mcp import create_mcp_server

        mcp = create_mcp_server(
            host=host,
            port=port,
            streamable_http_path="/",
            holder=holder,
        )
        mcp_sub_app = mcp.streamable_http_app()
        mcp_session_manager = mcp.session_manager

    @asynccontextmanager
    async def _lifespan(app: FastAPI):
        if mcp_session_manager is not None:
            async with mcp_session_manager.run():
                yield
        else:
            yield

    app = FastAPI(title="chemunited API", lifespan=_lifespan)

    app.dependency_overrides[get_project_holder] = lambda: holder

    app.include_router(ui_router)
    app.include_router(project_router)
    app.include_router(processes_router)
    app.include_router(protocols_read_router)
    app.include_router(protocols_write_router)
    app.include_router(runner_router)
    app.include_router(components_router)
    app.include_router(logs_router)
    app.include_router(monitoring_router)
    app.include_router(custom_router)
    app.include_router(export_router)

    if mcp_sub_app is not None:
        app.mount("/mcp", mcp_sub_app)

    if _WEB_DIR.is_dir():
        app.mount("/", StaticFiles(directory=_WEB_DIR), name="web")

    return app
