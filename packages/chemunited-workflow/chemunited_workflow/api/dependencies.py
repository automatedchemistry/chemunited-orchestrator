"""FastAPI dependency functions for the chemunited API."""

from __future__ import annotations

from fastapi import Depends, HTTPException

from .project_holder import ProjectHolder
from .services.monitoring import MonitoringService
from .services.protocol import ProtocolService
from .services.runner import RunnerService

_NO_PROJECT_MSG = (
    "No project loaded. Use PUT /project to load a project directory first."
)


def get_project_holder() -> ProjectHolder:
    raise NotImplementedError("Dependency not wired — was create_api() called?")


def get_protocol_service(
    holder: ProjectHolder = Depends(get_project_holder),
) -> ProtocolService:
    svc = holder.protocol_service
    if svc is None:
        raise HTTPException(status_code=503, detail=_NO_PROJECT_MSG)
    return svc


def get_runner_service(
    holder: ProjectHolder = Depends(get_project_holder),
) -> RunnerService:
    svc = holder.runner_service
    if svc is None:
        raise HTTPException(status_code=503, detail=_NO_PROJECT_MSG)
    return svc


def get_monitoring_service(
    holder: ProjectHolder = Depends(get_project_holder),
) -> MonitoringService:
    svc = holder.monitoring_service
    if svc is None:
        raise HTTPException(status_code=503, detail=_NO_PROJECT_MSG)
    return svc
