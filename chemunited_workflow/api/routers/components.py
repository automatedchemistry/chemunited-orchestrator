"""Routes: GET /components."""

import asyncio

import requests
from fastapi import APIRouter, Depends, HTTPException

from ...exceptions import DeviceCommunicationError
from ..dependencies import get_protocol_service
from ..schemas import ComponentCommandIn, ComponentCommandResult, ComponentStatus
from ..services.protocol import ProtocolService

router = APIRouter(prefix="/components", tags=["components"])


@router.get("/ping", response_model=list[ComponentStatus])
async def ping_components(
    timeout: float = 2.0,
    svc: ProtocolService = Depends(get_protocol_service),
):
    """Verify that all device URLs in ``associations.json`` are reachable."""
    return await asyncio.to_thread(svc.ping_components, timeout)


@router.get("/ping/{component}", response_model=ComponentStatus)
async def ping_component(
    component: str,
    timeout: float = 2.0,
    svc: ProtocolService = Depends(get_protocol_service),
):
    """Verify that a single configured device URL is reachable."""
    try:
        return await asyncio.to_thread(svc.ping_component, component, timeout)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/commands/{component}")
async def get_component_commands(
    component: str,
    timeout: float = 5.0,
    svc: ProtocolService = Depends(get_protocol_service),
):
    """Return the command metadata (verb + parameters) a component exposes."""
    try:
        return await asyncio.to_thread(svc.get_component_commands, component, timeout)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (requests.exceptions.RequestException, DeviceCommunicationError) as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Device unreachable or discovery failed: {exc}",
        ) from exc


@router.post(
    "/commands/{component}/{command:path}", response_model=ComponentCommandResult
)
async def send_component_command(
    component: str,
    command: str,
    body: ComponentCommandIn,
    timeout: float = 5.0,
    svc: ProtocolService = Depends(get_protocol_service),
):
    """Send a command directly to a component's device server and return the result."""
    try:
        return await asyncio.to_thread(
            svc.send_component_command,
            component,
            command,
            body.verb,
            body.params,
            body.body,
            timeout,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/")
async def get_components(svc: ProtocolService = Depends(get_protocol_service)):
    """Return the device connectivity map.

    Returns the full contents of `connectivity/associations.json` — the
    mapping of component names to their device-server URLs. Entries with an
    empty `component_url` are included as-is; they represent devices that are
    physically present but not yet wired to a server endpoint.
    """
    return svc.read_components()
