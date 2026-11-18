"""Exercise command lifetime through the real executor and runner, offline."""

import threading
from concurrent.futures import Future

import networkx as nx
import pytest
import requests
from pydantic import BaseModel

from chemunited_workflow import Process, WorkflowExecutor, compile_workflow
from chemunited_workflow.api.run_store import RunState, RunStore
from chemunited_workflow.api.services.runner import RunnerService
from chemunited_workflow.background import BackgroundCommandError
from chemunited_workflow.clients.http import BaseClient, ComponentClient
from chemunited_workflow.enums import NodeState, WorkflowEventType
from chemunited_workflow.platform import Platform


class Cfg(BaseModel):
    pass


def graph():
    value = nx.DiGraph()
    for name, tag in (("start", "start"), ("prepare", "script"), ("end", "end")):
        value.add_node(name, node_id=name, method=name, block_tag=tag)
    value.add_edge("start", "prepare", condition=True)
    value.add_edge("prepare", "end", condition=True)
    return value


def launch(fn):
    future = Future()

    def run():
        try:
            future.set_result(fn())
        except BaseException as exc:
            future.set_exception(exc)

    threading.Thread(target=run, daemon=True).start()
    return future


class AsyncProcess(Process[Cfg]):
    def build_workflow(self):
        return graph()

    def start(self, ctx):
        self.platform["Peltier"].put_async("temperature", temperature="-20 degC")
        return True

    def prepare(self, ctx):
        self.preparing.set()
        if self.fail:
            self.platform._wait(60)
        return True

    def end(self, ctx):
        return True


@pytest.mark.parametrize("resilient", [False, True])
def test_late_failure_identifies_submitter_without_blaming_observer(
    monkeypatch, resilient
):
    client = ComponentClient("http://instrument.test/peltier", component_ui="Peltier")
    preparing = threading.Event()
    cause = OSError("chiller unavailable")

    def transport(*args, **kwargs):
        assert preparing.wait(3)
        raise cause

    monkeypatch.setattr(client._session, "request", transport)
    process = AsyncProcess(Cfg(), Platform({"Peltier": client}))
    process.preparing, process.fail = preparing, True
    events = []
    executor = WorkflowExecutor(
        compile_workflow(graph()),
        process_key="glyc_0",
        error_resilient=resilient,
        event_listeners=[events.append],
    )
    execution = launch(lambda: executor.execute(process, "start"))
    try:
        with pytest.raises(BackgroundCommandError) as caught:
            execution.result(2)
        assert caught.value.origin.process == "glyc_0"
        assert caught.value.origin.node == "start"
        assert caught.value.origin.iteration == 0
        assert caught.value.__cause__ is cause
        assert executor._state.node_state[("start", 0)] == NodeState.COMPLETED
        assert executor._state.node_runtime[("prepare", 0)].error is None
        assert not [e for e in events if e.event_type == WorkflowEventType.NODE_FAILED]
        assert "chiller unavailable" in events[-1].message
    finally:
        process.platform.close_pending_commands(cancel=True)
        BaseClient.close(client)


def test_standalone_success_drains_and_same_platform_can_be_reused(monkeypatch):
    client = ComponentClient("http://instrument.test/peltier", component_ui="Peltier")
    release, entered = threading.Event(), threading.Event()

    def transport(*args, **kwargs):
        entered.set()
        assert release.wait(3)
        response = requests.Response()
        response.status_code, response._content = 200, b"{}"
        return response

    monkeypatch.setattr(client._session, "request", transport)
    process = AsyncProcess(Cfg(), Platform({"Peltier": client}))
    process.preparing, process.fail = threading.Event(), False
    executor = WorkflowExecutor(compile_workflow(graph()))
    execution = launch(lambda: executor.execute(process, "start"))
    try:
        assert entered.wait(1) and process.preparing.wait(1)
        assert not execution.done()
        release.set()
        assert not execution.result(1).errors
        assert process.platform._background.join(0) == []
        assert not executor.execute(process, "start").errors
        assert process.platform._background.join(0) == []
    finally:
        release.set()
        process.platform.close_pending_commands(cancel=True)
        BaseClient.close(client)


@pytest.mark.parametrize("fail", [False, True])
def test_runner_queue_spans_processes_and_drains_before_cancellation(
    tmp_path, monkeypatch, fail
):
    entered, second_started, release = (threading.Event() for _ in range(3))
    token_at_response = []
    client = ComponentClient("http://instrument.test/peltier", component_ui="Peltier")
    store = RunStore()
    run_id = store.try_start("proto.json")
    record = store.get()
    assert record is not None
    client._cancellation_token = record.cancel_event
    platform = Platform({"Peltier": client}, cancellation_token=record.cancel_event)

    def transport(*args, **kwargs):
        entered.set()
        assert release.wait(3)
        token_at_response.append(record.cancel_event.is_set())
        if fail:
            raise OSError("late response failed")
        response = requests.Response()
        response.status_code, response._content = 200, b"{}"
        return response

    monkeypatch.setattr(client._session, "request", transport)
    monkeypatch.setattr(
        Platform, "from_project_dir", classmethod(lambda cls, *a, **k: platform)
    )

    class First(Process[Cfg]):
        def build_workflow(self):
            return graph()

        def start(self, ctx):
            self.platform["Peltier"].put_async("temperature")
            assert entered.wait(1)
            return True

        def prepare(self, ctx):
            return True

        end = prepare

    class Second(Process[Cfg]):
        def build_workflow(self):
            return graph()

        def start(self, ctx):
            assert entered.is_set()
            assert not release.is_set()
            second_started.set()
            return True

        def prepare(self, ctx):
            return True

        end = prepare

    runner = RunnerService(
        tmp_path,
        {"first": First, "second": Second},
        {"first": Cfg, "second": Cfg},
        store,
    )
    execution = launch(
        lambda: runner._execute(
            run_id,
            "proto.json",
            [("first", 0), ("second", 0)],
            {"first_0": {}, "second_0": {}},
            dry_run=False,
            timeout_commands="1 s",
            error_resilient=True,
            record_monitoring=False,
        )
    )
    try:
        assert second_started.wait(2)
        assert not execution.done()
        assert not record.cancel_event.is_set()
        release.set()
        execution.result(2)
        assert token_at_response == [False]
        assert record.state == (RunState.FAILED if fail else RunState.FINISHED)
        assert platform._background.join(0) == []
    finally:
        release.set()
        platform.close_pending_commands(cancel=True)
        BaseClient.close(client)
