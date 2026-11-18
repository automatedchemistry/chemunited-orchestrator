"""Finite commands reuse the graph background host, with stricter completion rules."""

import threading
from concurrent.futures import Future

import pytest

from chemunited_workflow.background import (
    BackgroundCommandError,
    BackgroundTasks,
    CommandOrigin,
    command_origin_scope,
    current_command_origin,
)
from chemunited_workflow.cancellation import sleep_interruptibly, wait_while_paused
from chemunited_workflow.command_events import current_node
from chemunited_workflow.exceptions import RunCancelledError


def launch(fn):
    future = Future()

    def run():
        try:
            future.set_result(fn())
        except BaseException as exc:
            future.set_exception(exc)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return future


def submit(host, fn, key="p", **kwargs):
    return host.submit_command(
        fn, "test", key=key, component="Peltier", command="temperature", **kwargs
    )


def test_ordered_nonblocking_submission_and_independent_components():
    host = BackgroundTasks()
    entered, release = threading.Event(), threading.Event()
    calls = []

    def first():
        entered.set()
        assert release.wait(3)
        calls.append(1)
        assert host.in_command_worker("p")
        return 1

    try:
        a = submit(host, first)
        assert entered.wait(1)
        b = submit(host, lambda: calls.append(2))
        assert not a.done() and not b.done()
        assert submit(host, lambda: 3, key="other").result(1) == 3
        release.set()
        host.close_commands()
        assert a.result() == 1 and b.result() is None
        assert calls == [1, 2]
        assert host.join(0) == []
    finally:
        release.set()
        host.close_commands(cancel=True)


def test_critical_failure_retains_origin_and_cancels_queued_jobs():
    host = BackgroundTasks()
    entered, release = threading.Event(), threading.Event()
    cause = ValueError("controller failed")
    origin = CommandOrigin("glyc_0", "cool", 2)

    def fail():
        entered.set()
        assert release.wait(3)
        assert current_command_origin() == origin
        assert current_node() == "cool"
        raise cause

    with command_origin_scope(origin):
        failed = submit(host, fail)
    assert entered.wait(1)
    later = submit(host, lambda: pytest.fail("dispatched after failure"))
    release.set()
    try:
        with pytest.raises(BackgroundCommandError) as caught:
            failed.result(1)
        error = caught.value
        assert error.origin == origin and error.__cause__ is cause
        assert "glyc_0" in str(error) and "cool" in str(error)
        assert later.cancelled()
        with pytest.raises(BackgroundCommandError) as retained:
            host.check_command_errors()
        assert retained.value is error
    finally:
        host.close_commands(cancel=True)


def test_noncritical_failure_is_delivered_only_to_its_caller():
    host = BackgroundTasks()
    try:
        future = submit(host, lambda: 1 / 0, critical=False)
        with pytest.raises(ZeroDivisionError):
            future.result(1)
        host.check_command_errors()
        assert submit(host, lambda: 4).result(1) == 4
    finally:
        host.close_commands()


def test_close_drains_commands_without_waiting_for_background_graph_block():
    host = BackgroundTasks()
    graph_stop, graph_entered = threading.Event(), threading.Event()
    request_release, request_entered = threading.Event(), threading.Event()

    def graph():
        graph_entered.set()
        graph_stop.wait(3)

    def request():
        request_entered.set()
        assert request_release.wait(3)

    host.submit(graph, "monitor")
    submit(host, request)
    assert graph_entered.wait(1) and request_entered.wait(1)
    closing = launch(host.close_commands)
    try:
        assert not closing.done()
        request_release.set()
        closing.result(1)
        assert host.join(0) == ["background-monitor"]
    finally:
        request_release.set()
        graph_stop.set()
        assert host.join(2) == []


def test_cancel_prevents_dispatch_but_collects_inflight_request():
    host = BackgroundTasks()
    entered, release = threading.Event(), threading.Event()

    def inflight():
        entered.set()
        assert release.wait(3)

    running = submit(host, inflight)
    assert entered.wait(1)
    queued = submit(host, lambda: pytest.fail("cancelled request was sent"))
    cancelling = launch(lambda: host.close_commands(cancel=True))
    try:
        assert host._command_stop.wait(1)
        assert queued.cancelled()
        assert not cancelling.done()
        release.set()
        cancelling.result(1)
        assert running.done() and host.join(0) == []
        host.check_command_errors()
    finally:
        release.set()
        host.close_commands(cancel=True)


@pytest.mark.parametrize("paused", [False, True])
def test_failure_interrupts_cooperative_sleep_and_pause(paused):
    host = BackgroundTasks()
    pause = threading.Event()
    entered, release = threading.Event(), threading.Event()
    if paused:
        pause.set()

    def fail():
        entered.set()
        assert release.wait(3)
        raise OSError("offline")

    submit(host, fail)
    assert entered.wait(1)

    def waiting():
        if paused:
            wait_while_paused(pause, None, check_error=host.check_command_errors)
        else:
            sleep_interruptibly(60, None, check_error=host.check_command_errors)

    waiter = launch(waiting)
    release.set()
    try:
        with pytest.raises(BackgroundCommandError, match="offline"):
            waiter.result(1)
    finally:
        host.close_commands(cancel=True)


def test_cancelled_command_is_not_a_hardware_failure():
    host = BackgroundTasks()

    def cancelled():
        raise RunCancelledError("cancelled")

    try:
        with pytest.raises(RunCancelledError):
            submit(host, cancelled).result(1)
        host.check_command_errors()
    finally:
        host.close_commands(cancel=True)


def test_pending_barrier_surfaces_failure_before_cancelled_followup():
    host = BackgroundTasks()
    entered, release, barrier_entered = (threading.Event() for _ in range(3))

    def fail():
        entered.set()
        assert release.wait(3)
        raise OSError("original failure")

    submit(host, fail)
    assert entered.wait(1)
    submit(host, lambda: pytest.fail("followup was sent"))
    waiting = launch(lambda: host.wait_for_commands(checkpoint=barrier_entered.set))
    assert barrier_entered.wait(1)
    try:
        release.set()
        with pytest.raises(BackgroundCommandError, match="original failure"):
            waiting.result(1)
    finally:
        release.set()
        host.close_commands(cancel=True)
