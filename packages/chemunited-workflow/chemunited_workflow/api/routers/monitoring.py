"""Routes: GET /monitoring/discover, PUT/GET /monitoring/config, /monitoring/{state,start,stop,latest,history,recordings}."""

from __future__ import annotations

import requests
from fastapi import APIRouter, Depends, HTTPException

from ...exceptions import DeviceCommunicationError, MonitoringRunActiveError
from ..dependencies import get_monitoring_service
from ..schemas import MonitoringConfigIn, MonitoringStateOut
from ..services.monitoring import MonitoringService

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


@router.get("/discover/{component}")
async def discover_component(
    component: str,
    timeout: float = 5.0,
    svc: MonitoringService = Depends(get_monitoring_service),
):
    """List GET commands a component exposes, via the device server's live OpenAPI schema.

    Depends on the external device server serving `{server_url}/openapi.json`.
    Use the returned `command` values when registering variables via `PUT /monitoring/config`.
    """
    try:
        return svc.discover(component, timeout=timeout)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (requests.exceptions.RequestException, DeviceCommunicationError) as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Device unreachable or discovery failed: {exc}",
        )


@router.get("/config")
async def get_config(svc: MonitoringService = Depends(get_monitoring_service)):
    """Return the current monitoring registration (sample_time, request_timeout, variables)."""
    return svc.read_config()


@router.put("/config")
async def put_config(
    body: MonitoringConfigIn,
    svc: MonitoringService = Depends(get_monitoring_service),
):
    """Register which variables to monitor.

    Persisted to `connectivity/monitoring.json` so the registration survives a
    server restart. Does not start polling — call `POST /monitoring/start`
    to turn monitoring on against this config.
    """
    svc.write_config(body.model_dump())
    return svc.read_config()


@router.get("/state", response_model=MonitoringStateOut)
async def get_state(svc: MonitoringService = Depends(get_monitoring_service)):
    """Return the current monitoring state.

    `effective_on` is true whenever readings are being polled, whether from
    the manual toggle (`manual_on`) or because a protocol run has forced
    monitoring on (`run_active`). `recording`/`run_id` are set only while an
    active run has opted in to persisting readings to disk.
    """
    return svc.get_state()


@router.post("/start", response_model=MonitoringStateOut)
async def start_monitoring(svc: MonitoringService = Depends(get_monitoring_service)):
    """Turn monitoring on manually using the current registered config.

    Idempotent if already on. Returns 422 if no variables are registered,
    409 if a protocol run currently has monitoring forced on — the manual
    toggle isn't available while a run is active.
    """
    try:
        svc.start()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except MonitoringRunActiveError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return svc.get_state()


@router.post("/stop", response_model=MonitoringStateOut)
async def stop_monitoring(svc: MonitoringService = Depends(get_monitoring_service)):
    """Turn monitoring off manually. Idempotent if already off.

    Returns 409 if a protocol run currently has monitoring forced on.
    """
    try:
        svc.stop()
    except MonitoringRunActiveError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return svc.get_state()


@router.get("/latest")
async def get_latest(svc: MonitoringService = Depends(get_monitoring_service)):
    """Return the latest reading per registered variable — the live dashboard feed.

    Backed by an in-memory cache, one entry per variable, so this stays
    cheap regardless of how long monitoring has been on. Returns `{}` if
    nothing has been polled yet.
    """
    return svc.get_latest()


@router.get("/history/{component}/{command:path}")
async def get_history(
    component: str,
    command: str,
    svc: MonitoringService = Depends(get_monitoring_service),
):
    """Return the in-memory reading history for one variable, most recent last.

    Bounded to a fixed number of readings — this is the live visualization
    buffer, not a full recorded profile. Returns `[]` for a variable that
    hasn't been polled yet (never 404 — there's no session resource to be
    missing).
    """
    return svc.get_history(component, command)


@router.get("/recordings/{run_id}/{component}/{command:path}")
async def get_recording(
    run_id: str,
    component: str,
    command: str,
    tail: int | None = None,
    svc: MonitoringService = Depends(get_monitoring_service),
):
    """Read back the recorded profile for one variable from a past run.

    Returns every recorded reading (one entry per sampling tick, including
    failed/missed ticks with `error` set) for `component`/`command` in
    execution order, from `log/monitoring/{run_id}/`. Pass `?tail=N` to
    return only the last N readings. Only populated for runs started with
    `record_monitoring: true`.
    """
    try:
        return svc.read_recording(run_id, component, command, tail=tail)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
