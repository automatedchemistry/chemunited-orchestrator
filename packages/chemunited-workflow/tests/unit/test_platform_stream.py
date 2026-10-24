"""Unit tests for the live platform view's SSE stream."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from chemunited_workflow.api.device_state import DeviceStateStore
from chemunited_workflow.api.monitoring_store import MonitoringStore
from chemunited_workflow.api.routers.platform import _generate_platform_stream
from chemunited_workflow.command_events import CommandEvent


def _holder(*components: str) -> SimpleNamespace:
    return SimpleNamespace(
        device_state=DeviceStateStore(components),
        monitoring_store=MonitoringStore(),
    )


def _go_live(holder) -> None:
    holder.monitoring_store.try_manual_start()


def _command(holder, kind, call_id=1, component="valve") -> None:
    holder.device_state.observer()(
        CommandEvent(
            kind=kind, component=component, command="position", call_id=call_id
        )
    )


def _parse(frame: str) -> tuple[str | None, str, dict]:
    fields = dict(line.split(": ", 1) for line in frame.strip().splitlines())
    return fields.get("id"), fields["event"], json.loads(fields["data"])


def _stream(holder, **kwargs):
    kwargs.setdefault("poll_interval", 0.0)
    kwargs.setdefault("heartbeat_interval", 3600.0)
    return _generate_platform_stream(holder, **kwargs)


def _run(coro):
    return asyncio.run(coro)


def test_the_first_frame_is_a_snapshot_without_device_states_while_not_live():
    holder = _holder("valve")
    _command(holder, "started")

    async def first():
        return _parse(await anext(_stream(holder)))

    event_id, event, data = _run(first())

    assert event == "snapshot"
    assert data["live"] is False
    assert data["devices"] == {} and data["displays"] == {}
    assert event_id == f"{holder.device_state.epoch}-off"


def test_while_live_the_snapshot_has_every_device_then_updates_follow():
    holder = _holder("valve", "pump")
    _go_live(holder)

    async def frames():
        stream = _stream(holder)
        snapshot = _parse(await anext(stream))
        _command(holder, "started")
        update = _parse(await anext(stream))
        return snapshot, update

    (snap_id, snap_event, snap), (update_id, update_event, update) = _run(frames())

    epoch = holder.device_state.epoch
    assert (snap_event, snap_id) == ("snapshot", f"{epoch}-0")
    assert snap["live"] is True
    assert {name: d["status"] for name, d in snap["devices"].items()} == {
        "valve": "unknown",
        "pump": "unknown",
    }
    assert (update_event, update_id) == ("update", f"{epoch}-1")
    assert update["seq"] == 1
    assert update["devices"]["valve"]["status"] == "running"


def test_no_updates_go_out_until_live_then_a_full_snapshot_follows():
    holder = _holder("valve")

    async def frames():
        stream = _stream(holder)
        await anext(stream)  # not-live snapshot
        _command(holder, "started")
        _command(holder, "finished")
        _go_live(holder)
        return _parse(await anext(stream))

    _, event, data = _run(frames())

    assert event == "snapshot"
    assert data["live"] is True
    assert data["seq"] == 2
    assert data["devices"]["valve"]["status"] == "done"  # recorded while not live


def test_stopping_monitoring_sends_a_snapshot_without_device_states():
    holder = _holder("valve")
    _go_live(holder)

    async def frames():
        stream = _stream(holder)
        await anext(stream)
        holder.monitoring_store.try_manual_stop()
        return _parse(await anext(stream))

    event_id, event, data = _run(frames())

    assert event == "snapshot"
    assert data["live"] is False and data["devices"] == {}
    assert event_id.endswith("-off")


def test_a_run_alone_does_not_make_the_panel_live():
    holder = _holder("valve")
    holder.monitoring_store.begin_run("run-1", record=False)

    async def first():
        return _parse(await anext(_stream(holder)))

    _, _, data = _run(first())
    assert data["live"] is False


def test_reconnecting_with_last_event_id_replays_the_missed_updates():
    holder = _holder("valve")
    _go_live(holder)
    _command(holder, "started")
    _command(holder, "finished")
    epoch = holder.device_state.epoch

    async def first():
        return _parse(await anext(_stream(holder, last_event_id=f"{epoch}-1")))

    event_id, event, data = _run(first())

    assert (event, event_id) == ("update", f"{epoch}-2")
    assert data["devices"]["valve"]["status"] == "done"


def test_reconnecting_with_an_up_to_date_id_sends_nothing_until_a_change():
    holder = _holder("valve")
    _go_live(holder)
    _command(holder, "started")
    epoch = holder.device_state.epoch

    async def frames():
        stream = _stream(holder, last_event_id=f"{epoch}-1")
        pending = asyncio.ensure_future(anext(stream))
        await asyncio.sleep(0.05)
        assert not pending.done()
        _command(holder, "finished")
        return _parse(await pending)

    _, event, data = _run(frames())
    assert (event, data["seq"]) == ("update", 2)


def test_reconnecting_with_an_id_from_another_store_or_too_old_gets_a_snapshot():
    holder = _holder("valve")
    holder.device_state = DeviceStateStore(["valve"], log_size=1)
    _go_live(holder)
    _command(holder, "started")
    _command(holder, "finished")
    epoch = holder.device_state.epoch

    async def first(last_event_id):
        return _parse(await anext(_stream(holder, last_event_id=last_event_id)))

    for last_event_id in ("0000-1", f"{epoch}-0", f"{epoch}-off", "garbage"):
        _, event, data = _run(first(last_event_id))
        assert (event, data["seq"]) == ("snapshot", 2), last_event_id


def test_a_project_reload_starts_over_from_the_new_store():
    holder = _holder("valve")
    _go_live(holder)

    async def frames():
        stream = _stream(holder)
        await anext(stream)
        holder.device_state = DeviceStateStore(["pump"])
        return _parse(await anext(stream))

    event_id, event, data = _run(frames())

    assert event == "snapshot"
    assert list(data["devices"]) == ["pump"]
    assert event_id == f"{holder.device_state.epoch}-0"


def test_a_heartbeat_follows_a_quiet_interval():
    holder = _holder("valve")

    async def frames():
        stream = _stream(holder, heartbeat_interval=0.0)
        await anext(stream)
        return _parse(await anext(stream))

    event_id, event, data = _run(frames())
    assert (event_id, event, data) == (None, "heartbeat", {"live": False})


def test_lcd_values_go_out_only_while_live():
    holder = SimpleNamespace(
        device_state=DeviceStateStore(displays={"Flow": "pump::value"}),
        monitoring_store=MonitoringStore(),
    )
    reading = {"time": "t", "value": 2.5, "error": None}

    async def frames():
        stream = _stream(holder)
        await anext(stream)  # not-live snapshot: no LCD values
        holder.device_state.record_reading("pump::value", reading)
        _go_live(holder)
        snapshot = _parse(await anext(stream))
        holder.device_state.record_reading("pump::value", {**reading, "value": 3})
        update = _parse(await anext(stream))
        return snapshot, update

    (_, _, snapshot), (_, event, update) = _run(frames())

    assert snapshot["displays"]["Flow"]["value"] == "2.5"
    assert event == "update"
    assert update["displays"]["Flow"]["value"] == "3"
