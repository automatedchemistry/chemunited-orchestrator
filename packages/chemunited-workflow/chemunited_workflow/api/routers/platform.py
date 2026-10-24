"""Routes: GET /platform/state, GET /platform/stream — the live platform view."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse

from ..dependencies import get_project_holder
from ..device_state import DeviceStateStore
from ..project_holder import ProjectHolder

router = APIRouter(prefix="/platform", tags=["platform"])
STREAM_POLL_INTERVAL_SECONDS = 0.1
STREAM_HEARTBEAT_INTERVAL_SECONDS = 5.0

_NO_PROJECT_MSG = (
    "No project loaded. Use PUT /project to load a project directory first."
)


def _store(holder: ProjectHolder) -> DeviceStateStore:
    store = holder.device_state
    if store is None:
        raise HTTPException(status_code=503, detail=_NO_PROJECT_MSG)
    return store


def _is_live(holder: ProjectHolder) -> bool:
    """Live while monitoring is on from the Monitoring page — not merely for a run."""
    return bool(holder.monitoring_store.snapshot()["manual_on"])


def _snapshot(store: DeviceStateStore, live: bool) -> dict[str, Any]:
    snapshot = {"live": live, **store.snapshot()}
    if not live:
        # Device states and LCD values go out only while live.
        snapshot["devices"] = {}
        snapshot["displays"] = {}
    return snapshot


def _frame(event: str, data: dict[str, Any], event_id: str | None = None) -> str:
    head = f"id: {event_id}\n" if event_id is not None else ""
    return f"{head}event: {event}\ndata: {json.dumps(data)}\n\n"


def _event_id(store: DeviceStateStore, seq: int, live: bool) -> str:
    # Only a live frame's id can be resumed from: a browser that last saw the
    # panel not live has no device states to apply a replay to.
    return f"{store.epoch}-{seq}" if live else f"{store.epoch}-off"


def _resume_from(store: DeviceStateStore, last_event_id: str | None) -> int | None:
    """The seq to replay from, if *last_event_id* is a live frame of *store*."""
    if not last_event_id:
        return None
    epoch, _, seq = last_event_id.partition("-")
    if epoch != store.epoch or not seq.isdigit():
        return None
    return int(seq)


@router.get("/state")
async def get_state(holder: ProjectHolder = Depends(get_project_holder)):
    """Return the live state of every device and LCD display.

    `live` is true while monitoring is on from the Monitoring page; device
    states and display values are only included while live. Each device has
    a `status` (`unknown`, `running`, `done` or `failed`), its last `command`
    (name, params, ISO time, run and node), and its `picture` when the server
    can draw one (`pictures` is false without the `live` extra).
    """
    return _snapshot(_store(holder), _is_live(holder))


@router.get("/stream")
async def stream_state(
    holder: ProjectHolder = Depends(get_project_holder),
    last_event_id: str | None = Header(default=None),
):
    """Stream the live platform state as Server-Sent Events.

    The first frame is a full `snapshot` (the same body as `/platform/state`),
    followed by an `update` frame for each change, `{"seq", "devices"}` or
    `{"seq", "displays"}`, with `id: <epoch>-<seq>`. A browser that
    reconnects with `Last-Event-ID` gets the updates it missed, or a new
    snapshot if they are no longer in the server's log. A new snapshot also
    follows whenever `live` changes or the project is reloaded. A `heartbeat`
    frame arrives after 5 s without other frames.
    """
    _store(holder)
    return StreamingResponse(
        _generate_platform_stream(holder, last_event_id=last_event_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


async def _generate_platform_stream(
    holder: ProjectHolder,
    *,
    last_event_id: str | None = None,
    poll_interval: float = STREAM_POLL_INTERVAL_SECONDS,
    heartbeat_interval: float = STREAM_HEARTBEAT_INTERVAL_SECONDS,
) -> AsyncIterator[str]:
    store = holder.device_state
    if store is None:
        return
    live = _is_live(holder)

    cursor: int | None = None
    resume = _resume_from(store, last_event_id) if live else None
    if resume is not None:
        missed = store.changes_since(resume)
        if missed is not None:
            for change in missed:
                yield _frame("update", change, _event_id(store, change["seq"], True))
            cursor = missed[-1]["seq"] if missed else resume
    if cursor is None:
        snapshot = _snapshot(store, live)
        cursor = snapshot["seq"]
        yield _frame("snapshot", snapshot, _event_id(store, cursor, live))

    last_sent = time.monotonic()
    while True:
        await asyncio.sleep(poll_interval)
        sent = False
        current = holder.device_state or store
        now_live = _is_live(holder)
        changes = None
        if current is store and now_live == live:
            changes = store.changes_since(cursor) if live else []
        if changes is None:
            # The project was reloaded, `live` changed, or this stream fell
            # further behind than the log reaches: start over from a snapshot.
            store, live = current, now_live
            snapshot = _snapshot(store, live)
            cursor = snapshot["seq"]
            yield _frame("snapshot", snapshot, _event_id(store, cursor, live))
            sent = True
        else:
            for change in changes:
                cursor = change["seq"]
                yield _frame("update", change, _event_id(store, cursor, True))
                sent = True

        now = time.monotonic()
        if sent:
            last_sent = now
        elif now - last_sent >= heartbeat_interval:
            yield _frame("heartbeat", {"live": live})
            last_sent = now
