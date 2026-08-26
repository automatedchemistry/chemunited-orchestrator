"""Tests for the tray module.

Covers:
- _display_host(): normalizes 0.0.0.0/IPv6/plain hosts
- _create_tray_badge_icon(): returns an RGBA Pillow image
- _stop_running_simulation(): joins the worker thread and marks IDLE when
  RUNNING, no-op otherwise
"""

from __future__ import annotations

import queue
import threading
from pathlib import Path

import pytest

from chemunited_sim.cli.clock import SimClock
from chemunited_sim.cli.server import SimStatus, SimulationState
from chemunited_sim.cli.tray import _display_host, _stop_running_simulation
from chemunited_sim.worker.config import SimConfig


def _make_state(
    sim_status: SimStatus, worker_thread: threading.Thread | None
) -> SimulationState:
    return SimulationState(
        sim_status=sim_status,
        current_t=0.0,
        config=SimConfig(),
        db_path=None,
        project=None,
        clock=SimClock(),
        cmd_queue=queue.Queue(),
        db_dir=Path("./simulations/"),
        _worker_thread=worker_thread,
    )


# ---------------------------------------------------------------------------
# _display_host
# ---------------------------------------------------------------------------


def test_display_host_plain_hostname_unchanged():
    assert _display_host("localhost") == "localhost"


def test_display_host_unspecified_ipv4_becomes_loopback():
    assert _display_host("0.0.0.0") == "127.0.0.1"


def test_display_host_ipv6_wrapped_in_brackets():
    assert _display_host("::1") == "[::1]"


# ---------------------------------------------------------------------------
# _create_tray_badge_icon
# ---------------------------------------------------------------------------


def test_tray_badge_icon_is_rgba():
    pytest.importorskip("PIL")
    from chemunited_sim.cli.tray import _create_tray_badge_icon

    icon = _create_tray_badge_icon(size=64)
    assert icon.mode == "RGBA"
    assert icon.size == (64, 64)


# ---------------------------------------------------------------------------
# _stop_running_simulation
# ---------------------------------------------------------------------------


def test_stop_running_simulation_joins_worker_and_marks_idle():
    worker_thread = threading.Thread(target=lambda: None)
    worker_thread.start()
    worker_thread.join()

    state = _make_state(SimStatus.RUNNING, worker_thread)
    _stop_running_simulation(state)

    assert state._stop_event.is_set()
    assert state.sim_status == SimStatus.IDLE


def test_stop_running_simulation_is_noop_when_idle():
    state = _make_state(SimStatus.IDLE, worker_thread=None)
    _stop_running_simulation(state)

    assert not state._stop_event.is_set()
    assert state.sim_status == SimStatus.IDLE
